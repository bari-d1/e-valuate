"""
app.services.tracking
---------------------
Monitoring and chasing for evaluations that use assembled question sets: each
participant's status and progress, the evaluation summary, the timeline,
consultant actions (remind, resend or regenerate a link, extend the deadline,
reopen a form, close the evaluation) and automatic reminders.

Status (one per participant):
  Not ready      their set isn't approved
  Ready to send  approved, but no email has gone yet
  Sent           their link has been emailed
  Opened         they've opened the form
  In progress    at least one answer saved
  Submitted      submitted
  Email failed   the last email to them failed and nothing has gone through since
                 (shown instead of Sent; once they've opened the form, the failure
                 is shown beside their status instead)

Progress is answered / required visible questions from the portal's own
progress_of, so it always matches what the participant sees and the submit check.

Everything for an evaluation is loaded in a fixed number of queries
(load_rows), whatever the number of participants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.board_member_profile import governance_role_from_participant_role
from app.db.models import (
    AssessmentAssignment,
    Evaluation,
    Participant,
    ParticipantEvent,
    ParticipantQuestionSet,
    Question,
    QuestionBankItem,
    Response,
)
from app.services import participant_events as events
from app.services import participant_portal as form
from app.services import reminder_schedule as sched
from app.services.email_service import is_reserved_address
from app.services.question_selection import ROLE_LABELS

STATUS_LABELS = {
    "not_ready": "Not ready", "ready": "Ready to send", "sent": "Sent", "opened": "Opened",
    "in_progress": "In progress", "submitted": "Submitted", "email_failed": "Email failed",
}
OUTSTANDING = ("sent", "email_failed", "opened", "in_progress")  # have a link, haven't submitted


class TrackingError(ValueError):
    """An action that isn't allowed now. The message is safe to show the consultant."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ----------------------------
# Loading an evaluation's state
# ----------------------------

@dataclass
class Row:
    participant: Participant
    pset: Optional[ParticipantQuestionSet]
    assignment: Optional[AssessmentAssignment]
    progress: Dict[str, int]
    has_answers: bool
    events: List[ParticipantEvent] = field(default_factory=list)

    # Derived from events
    @property
    def first_sent_at(self) -> Optional[datetime]:
        return next((e.created_at for e in self.events if e.event_type in events.EMAIL_SENT), None) \
            or (self.assignment.email_sent_at if self.assignment else None)

    @property
    def last_email(self) -> Optional[ParticipantEvent]:
        return next((e for e in reversed(self.events)
                     if e.event_type in events.EMAIL_SENT or e.event_type == events.EMAIL_FAILED), None)

    @property
    def reminders(self) -> List[ParticipantEvent]:
        """Reminders that went out (deadline-extension notices don't count towards the maximum)."""
        return [e for e in self.events if e.event_type == "reminder_sent" and (e.detail or {}).get("kind") != "deadline"]

    @property
    def last_reminder_at(self) -> Optional[datetime]:
        tried = [e.created_at for e in self.events if e.event_type == "reminder_sent"
                 or (e.event_type == events.EMAIL_FAILED and (e.detail or {}).get("kind") == "reminder_sent")]
        return max(tried) if tried else None

    @property
    def sent_keys(self) -> set:
        prefix = f"{self.assignment.id}:" if self.assignment else "-"
        return {e.dedupe_key[len(prefix):] for e in self.events if e.dedupe_key and e.dedupe_key.startswith(prefix)}

    @property
    def status(self) -> str:
        if self.pset is None or self.pset.status == "draft":
            return "not_ready"
        a = self.assignment
        if a is not None and a.submitted_at:
            return "submitted"
        if self.has_answers:
            return "in_progress"
        if a is not None and a.opened_at:
            return "opened"
        last = self.last_email
        if last is not None and last.event_type == events.EMAIL_FAILED:
            return "email_failed"
        if last is not None or (a is not None and a.email_sent_at):
            return "sent"
        return "ready"

    @property
    def email_error(self) -> Optional[str]:
        last = self.last_email
        return (last.detail or {}).get("error") if last is not None and last.event_type == events.EMAIL_FAILED else None


def load_rows(db: Session, ev: Evaluation) -> List[Row]:
    """Every participant's state in seven queries, whatever the number of participants."""
    participants = db.execute(select(Participant).where(Participant.evaluation_id == ev.id)
                              .order_by(Participant.created_at, Participant.id)).scalars().all()
    sets = {s.participant_id: s for s in db.execute(select(ParticipantQuestionSet).where(
        ParticipantQuestionSet.evaluation_id == ev.id)).scalars()}
    assignments = {a.respondent_participant_id: a for a in db.execute(select(AssessmentAssignment).where(
        AssessmentAssignment.evaluation_id == ev.id, AssessmentAssignment.assignment_type == form.ASSEMBLED)).scalars()}
    questions = db.execute(select(Question).where(
        Question.evaluation_id == ev.id, Question.participant_id.is_not(None),
        Question.status.in_(("approved", "locked"))).order_by(Question.sort_order, Question.id)).scalars().all()
    item_ids = {q.bank_item_id for q in questions if q.bank_item_id}
    items = {i.id: i for i in db.execute(select(QuestionBankItem).where(QuestionBankItem.id.in_(item_ids))).scalars()} \
        if item_ids else {}
    responses = db.execute(select(Response).where(
        Response.evaluation_id == ev.id,
        Response.assignment_id.in_([a.id for a in assignments.values()]))).scalars().all() if assignments else []
    evs = db.execute(select(ParticipantEvent).where(ParticipantEvent.evaluation_id == ev.id)
                     .order_by(ParticipantEvent.created_at, ParticipantEvent.id)).scalars().all()

    by_participant: Dict[Any, List[Question]] = {}
    for q in questions:
        by_participant.setdefault(q.participant_id, []).append(q)
    by_assignment: Dict[Any, List[Response]] = {}
    for r in responses:
        by_assignment.setdefault(r.assignment_id, []).append(r)
    events_by: Dict[Any, List[ParticipantEvent]] = {}
    for e in evs:
        if e.participant_id:
            events_by.setdefault(e.participant_id, []).append(e)

    rows = []
    for p in participants:
        a = assignments.get(p.id)
        qs = by_participant.get(p.id, [])
        q_by_id = {str(q.id): q for q in qs}
        rs = by_assignment.get(a.id, []) if a else []
        answers = {str(r.question_id): form.answer_value(r, q_by_id[str(r.question_id)])
                   for r in rs if str(r.question_id) in q_by_id}
        rows.append(Row(participant=p, pset=sets.get(p.id), assignment=a,
                        progress=form.progress_of(qs, items, answers), has_answers=bool(rs),
                        events=events_by.get(p.id, [])))
    return rows


# ----------------------------
# Summary
# ----------------------------

def settings_of(ev: Evaluation) -> Dict[str, Any]:
    return sched.effective_settings(ev.reminder_settings)


def _slots(row: Row, ev: Evaluation, settings: Dict[str, Any]) -> List[sched.Slot]:
    first = row.first_sent_at
    return sched.schedule(settings, first.date(), ev.deadline) if first else []


def _days_left(ev: Evaluation, today: date) -> Optional[int]:
    return (ev.deadline - today).days if ev.deadline else None


def participant_dict(row: Row, ev: Evaluation, settings: Dict[str, Any], today: date) -> Dict[str, Any]:
    p, a, status = row.participant, row.assignment, row.status
    next_on = None
    if settings["enabled"] and status in OUTSTANDING and ev.status != "closed":
        next_on = sched.next_slot_on(_slots(row, ev, settings), today, row.sent_keys)
    reminders = row.reminders
    return {
        "participant_id": str(p.id), "name": p.full_name or p.email, "email": p.email,
        "role": ROLE_LABELS.get(governance_role_from_participant_role(p.role) or "") or p.role or "",
        "status": status, "status_label": STATUS_LABELS[status],
        "email_error": row.email_error,
        "progress": {"answered": row.progress["required_answered"], "required": row.progress["required"]},
        "sent_at": _iso(row.first_sent_at), "last_sent_at": _iso(a.email_sent_at if a else None),
        "opened_at": _iso(a.opened_at if a else None), "last_activity_at": _iso(a.last_activity_at if a else None),
        "submitted_at": _iso(a.submitted_at if a else None),
        "reminders_sent": len(reminders), "last_reminder_at": _iso(reminders[-1].created_at if reminders else None),
        "next_reminder_on": next_on.isoformat() if next_on else None,
        "days_left": _days_left(ev, today),
    }


def summary(db: Session, ev: Evaluation, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or _now()
    today = now.date()
    settings = settings_of(ev)
    rows = load_rows(db, ev)
    people = [participant_dict(r, ev, settings, today) for r in rows]
    counts = {k: 0 for k in STATUS_LABELS}
    for x in people:
        counts[x["status"]] += 1
    ready = [x for x in people if x["status"] != "not_ready"]
    required = sum(x["progress"]["required"] for x in ready)
    answered = sum(x["progress"]["answered"] for x in ready)
    nexts = [x["next_reminder_on"] for x in people if x["next_reminder_on"]]
    return {
        "evaluation": {
            "evaluation_id": ev.id, "name": form.evaluation_title(ev), "status": ev.status,
            "open": ev.status != "closed", "deadline": ev.deadline.isoformat() if ev.deadline else None,
            "days_left": _days_left(ev, today),
        },
        "counts": counts,
        "status_labels": STATUS_LABELS,
        "participants_total": len(people),
        "submitted": counts["submitted"],
        "completion_percent": round(100 * answered / required) if required else 0,
        "reminders": {"enabled": settings["enabled"], "next_batch_on": min(nexts) if nexts else None},
        "participants": people,
    }


# ----------------------------
# Timeline
# ----------------------------

def _d(iso: Optional[str]) -> str:
    return date.fromisoformat(iso).strftime("%d %b %Y").lstrip("0") if iso else "no deadline"


def describe(e: ParticipantEvent) -> str:
    """One event in plain words."""
    d = e.detail or {}
    kind = {"invite_sent": "invitation", "link_resent": "link", "reminder_sent": "reminder"}
    text = {
        "invite_sent": "Invitation sent",
        "link_resent": "New link sent" if d.get("new_link") else "Link sent again",
        "reminder_sent": ("Deadline extension notice sent" if d.get("kind") == "deadline"
                          else "Final reminder sent" if d.get("final")
                          else "Automatic reminder sent" if d.get("kind") == "automatic" else "Reminder sent"),
        "email_failed": f"The {kind.get(d.get('kind'), 'email')} couldn't be sent: {d.get('error') or 'unknown error'}",
        "opened": "Opened the form",
        "first_answer": "Answered their first question",
        "submitted": "Submitted their answers",
        "link_regenerated": "Created a new link; the old one stopped working",
        "deadline_extended": f"Deadline changed from {_d(d.get('from'))} to {_d(d.get('to'))}",
        "form_reopened": f"Reopened their form for changes: {d.get('reason')}",
        "evaluation_closed": "Closed the evaluation to new answers",
        "evaluation_reopened": "Reopened the evaluation",
        "reminder_settings_changed": ("Turned automatic reminders on" if d.get("enabled") is True
                                      else "Turned automatic reminders off" if d.get("enabled") is False
                                      else "Changed the reminder schedule"),
    }.get(e.event_type, e.event_type)
    return text


def timeline(db: Session, ev: Evaluation, participant: Participant) -> List[Dict[str, Any]]:
    """The participant's events and evaluation-wide ones (deadline, close), oldest first."""
    rows = db.execute(select(ParticipantEvent).where(
        ParticipantEvent.evaluation_id == ev.id,
        (ParticipantEvent.participant_id == participant.id) | (ParticipantEvent.participant_id.is_(None)))
        .order_by(ParticipantEvent.created_at, ParticipantEvent.id)).scalars().all()
    return [{"id": str(e.id), "at": _iso(e.created_at), "type": e.event_type, "text": describe(e),
             "actor": {"system": "Automatic", "participant": "Participant"}.get(e.actor, e.actor),
             "evaluation_wide": e.participant_id is None} for e in rows]


# ----------------------------
# Reminders (manual and automatic)
# ----------------------------

def _reminder_content(db: Session, ev: Evaluation, row: Row, **flags: Any) -> Dict[str, Any]:
    p = row.participant
    return dict(
        full_name=p.full_name, form_url=form.form_link(row.assignment), organisation=form.organisation_name(db, ev),
        evaluation_name=form.evaluation_title(ev), consultancy=form.consultancy_name(),
        answered=row.progress["required_answered"], required=row.progress["required"],
        estimated_minutes=row.pset.estimated_minutes if row.pset else None, deadline=ev.deadline,
        notice=form.participant_notice(ev), **flags,
    )


def _send_reminder(db: Session, ev: Evaluation, row: Row, actor: str, *, kind: str, final: bool = False,
                   deadline_extended: bool = False, dedupe_key: Optional[str] = None,
                   slot: Optional[str] = None, at: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Send one reminder and record it. With a dedupe_key (automatic reminders) the event is written
    first, in a savepoint: if another run already holds that key the unique index refuses it and
    nothing is sent. The insert waits for a concurrent run's uncommitted claim, so two runs at once
    can't both send.
    """
    from app.services.email_service import send_form_reminder_email  # tests patch it here

    p, a = row.participant, row.assignment
    claim = None
    if dedupe_key:
        try:
            with db.begin_nested():
                claim = events.record(db, ev.id, "reminder_sent", actor, participant_id=p.id, assignment_id=a.id,
                                      dedupe_key=dedupe_key, at=at, kind=kind, final=final or None, slot=slot,
                                      outcome="pending")
        except IntegrityError:
            return {"outcome": "skipped", "reason": "Already sent by another run."}
    ok, err = send_form_reminder_email(
        p.email, **_reminder_content(db, ev, row, final=final, deadline_extended=deadline_extended))
    if claim is not None:
        if ok:
            claim.detail = {**claim.detail, "outcome": "sent"}
        else:  # keep the key so the slot isn't retried; the failure shows on their status
            claim.event_type = events.EMAIL_FAILED
            claim.detail = {"kind": "reminder_sent", "final": final or None, "slot": slot,
                            "error": events.short_error(err)}
        db.flush()
    elif ok:
        events.record(db, ev.id, "reminder_sent", actor, participant_id=p.id, assignment_id=a.id, at=at, kind=kind,
                      final=final or None)
    else:
        events.record(db, ev.id, events.EMAIL_FAILED, actor, participant_id=p.id, assignment_id=a.id, at=at,
                      kind="reminder_sent", error=events.short_error(err))
    return {"outcome": "sent" if ok else "failed", "reason": None if ok else events.short_error(err)}


def remind_block(ev: Evaluation, row: Row, now: datetime, override: bool) -> Optional[str]:
    """Why a manual reminder can't go to this participant now (None if it can). Override only lifts the 24-hour rule."""
    status = row.status
    if ev.status == "closed":
        return "The evaluation is closed."
    if status == "not_ready":
        return "Their question set isn't approved yet."
    if status == "submitted":
        return "They've already submitted."
    if status == "ready" or row.assignment is None:
        return "They haven't been sent their link yet."
    last = row.last_reminder_at
    if not override and last is not None and now - last < sched.MIN_GAP:
        return "Reminded less than 24 hours ago."
    return None


def remind(db: Session, ev: Evaluation, actor: str, participant_ids: Optional[Iterable[str]] = None, *,
           override: bool = False, dry_run: bool = False, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Remind some participants now (default: everyone outstanding). Per participant: sent, failed,
    skipped (with the reason) or, in a dry run, would_send. The in-page confirmation uses the dry run.
    """
    now = now or _now()
    rows = load_rows(db, ev)
    wanted = {str(x) for x in participant_ids} if participant_ids is not None else None
    out = []
    for row in rows:
        pid = str(row.participant.id)
        if wanted is not None and pid not in wanted:
            continue
        if wanted is None and row.status not in OUTSTANDING:
            continue
        base = {"participant_id": pid, "name": row.participant.full_name or row.participant.email}
        reason = remind_block(ev, row, now, override)
        if reason:
            out.append({**base, "outcome": "skipped", "reason": reason})
        elif dry_run:
            out.append({**base, "outcome": "would_send", "reason": None})
        else:
            out.append({**base, **_send_reminder(db, ev, row, actor, kind="manual", at=now)})
    return out


def _due(ev: Evaluation, row: Row, settings: Dict[str, Any], now: datetime):
    """(slot, why) for automatic reminders, or (None, why not)."""
    if row.status not in OUTSTANDING:
        return None, None
    if ev.status == "closed":
        return None, "The evaluation is closed."
    if row.status == "email_failed":
        return None, "The last email to them failed; fix the address or resend the link first."
    if is_reserved_address(row.participant.email):
        return None, "Reserved test address; never emailed."
    slots = _slots(row, ev, settings)
    return sched.due_slot(settings, slots, now.date(), deadline=ev.deadline, sent_keys=row.sent_keys,
                          reminders_sent=len(row.reminders), last_reminder_at=row.last_reminder_at, now=now)


def due_list(db: Session, ev: Evaluation, now: datetime, *, settings: Optional[Dict[str, Any]] = None
             ) -> Dict[str, List[Dict[str, Any]]]:
    """Who would be reminded automatically today and why, and who wouldn't (dry run, for any settings)."""
    settings = settings or settings_of(ev)
    would, skipped = [], []
    for row in load_rows(db, ev):
        slot, why = _due(ev, row, settings, now)
        if why is None:
            continue
        item = {"participant_id": str(row.participant.id), "name": row.participant.full_name or row.participant.email,
                "status": row.status, "reason": why}
        (would if slot else skipped).append({**item, "final": bool(slot and slot.final)})
    return {"would_remind": would, "skipped": skipped}


def send_due_reminders(db: Session, now: Optional[datetime] = None, *, dry_run: bool = False,
                       evaluation_id: Optional[str] = None, commit: bool = True) -> Dict[str, Any]:
    """
    Send every automatic reminder due now, across open evaluations with reminders switched on.
    Safe to run repeatedly and concurrently: each slot is claimed under a unique key before
    sending (see _send_reminder), and each participant is committed on its own so a slow run
    never holds another one up for long. Never reminds submitted participants, closed
    evaluations, unapproved sets or reserved test addresses.
    """
    now = now or _now()
    stmt = select(Evaluation).where(Evaluation.status != "closed")
    if evaluation_id:
        stmt = stmt.where(Evaluation.id == evaluation_id)
    out: Dict[str, Any] = {"now": now.isoformat(), "dry_run": dry_run, "evaluations": 0,
                           "sent": [], "failed": [], "skipped": [], "would_remind": []}
    for ev in db.execute(stmt.order_by(Evaluation.id)).scalars().all():
        settings = settings_of(ev)
        if not settings["enabled"] or not form.uses_assembled_sets(db, ev.id):
            continue
        out["evaluations"] += 1
        for row in load_rows(db, ev):
            slot, why = _due(ev, row, settings, now)
            if why is None:
                continue
            item = {"evaluation_id": ev.id, "participant_id": str(row.participant.id),
                    "name": row.participant.full_name or row.participant.email, "reason": why}
            if slot is None:
                out["skipped"].append(item)
                continue
            if dry_run:
                out["would_remind"].append({**item, "final": slot.final})
                continue
            res = _send_reminder(db, ev, row, "system", kind="automatic", final=slot.final, slot=slot.key,
                                 dedupe_key=f"{row.assignment.id}:{slot.key}", at=now)
            bucket = res["outcome"] if res["outcome"] in ("sent", "failed") else "skipped"
            out[bucket].append({**item, "final": slot.final, **({"reason": res["reason"]} if res["reason"] else {})})
            if commit:
                db.commit()
    return out


# ----------------------------
# Links, deadline, reopening and closing
# ----------------------------

def _row(db: Session, ev: Evaluation, participant_id) -> Row:
    row = next((r for r in load_rows(db, ev) if str(r.participant.id) == str(participant_id)), None)
    if row is None:
        raise TrackingError("Participant not found in this evaluation.")
    return row


def _require_sendable(ev: Evaluation, row: Row) -> None:
    if ev.status == "closed":
        raise TrackingError("The evaluation is closed; reopen it before sending links.")
    if row.status == "not_ready":
        raise TrackingError("Their question set isn't approved yet.")


def resend_link(db: Session, ev: Evaluation, participant_id, actor: str) -> Dict[str, Any]:
    """The same link again, as a fresh invitation."""
    row = _row(db, ev, participant_id)
    _require_sendable(ev, row)
    if row.status == "submitted":
        raise TrackingError("They've already submitted.")
    sent = form.send_form_link(db, ev, row.participant, actor=actor, event_type="link_resent")
    return {"sent": sent["sent"], "error": sent["error"]}


def regenerate_link(db: Session, ev: Evaluation, participant_id, actor: str) -> Dict[str, Any]:
    """A new token (the old link stops working at once), then send it. Saved answers stay."""
    row = _row(db, ev, participant_id)
    _require_sendable(ev, row)
    a = row.assignment or form.ensure_form_assignment(db, row.participant, row.pset)
    a.access_token, a.token_created_at = form.new_token(db), _now()
    events.record(db, ev.id, "link_regenerated", actor, participant_id=row.participant.id, assignment_id=a.id)
    db.flush()
    if row.status == "submitted":
        return {"sent": False, "error": None}
    sent = form.send_form_link(db, ev, row.participant, actor=actor, event_type="link_resent", new_link=True)
    return {"sent": sent["sent"], "error": sent["error"]}


def set_deadline(db: Session, ev: Evaluation, new: date, actor: str, *, notify: bool = False,
                 now: Optional[datetime] = None) -> Dict[str, Any]:
    """Change the deadline (not into the past); optionally tell everyone outstanding."""
    now = now or _now()
    if new < now.date():
        raise TrackingError("The deadline can't be in the past.")
    old = ev.deadline
    ev.deadline = new
    events.record(db, ev.id, "deadline_extended", actor, **{"from": old.isoformat() if old else None,
                                                             "to": new.isoformat(), "notified": notify or None})
    db.flush()
    results = []
    if notify and ev.status != "closed":
        for row in load_rows(db, ev):
            if row.status in OUTSTANDING:
                results.append({"participant_id": str(row.participant.id), "name": row.participant.full_name,
                                **_send_reminder(db, ev, row, actor, kind="deadline", deadline_extended=True)})
    return {"deadline": new.isoformat(), "notified": results}


def reopen_form(db: Session, ev: Evaluation, participant_id, reason: str, actor: str) -> Dict[str, Any]:
    """Let one participant change their submitted answers. Their question set stays locked."""
    if not (reason or "").strip():
        raise ValueError("Give a reason for reopening their form.")
    row = _row(db, ev, participant_id)
    a = row.assignment
    if a is None or not a.submitted_at:
        raise TrackingError("Only a submitted form can be reopened.")
    a.submitted_at, a.responded_at, a.status = None, None, "invited"
    row.participant.status, row.participant.responded_at = "invited", None
    events.record(db, ev.id, "form_reopened", actor, participant_id=row.participant.id, assignment_id=a.id,
                  reason=reason.strip())
    db.flush()
    return {"status": "in_progress" if row.has_answers else "opened"}


def close_evaluation(db: Session, ev: Evaluation, actor: str) -> Dict[str, Any]:
    if ev.status == "closed":
        raise TrackingError("The evaluation is already closed.")
    events.record(db, ev.id, "evaluation_closed", actor, previous=ev.status)
    ev.status = "closed"
    db.flush()
    return {"status": ev.status}


def reopen_evaluation(db: Session, ev: Evaluation, actor: str) -> Dict[str, Any]:
    if ev.status != "closed":
        raise TrackingError("The evaluation isn't closed.")
    last = db.execute(select(ParticipantEvent).where(
        ParticipantEvent.evaluation_id == ev.id, ParticipantEvent.event_type == "evaluation_closed")
        .order_by(ParticipantEvent.created_at.desc()).limit(1)).scalars().first()
    previous = ((last.detail or {}).get("previous") if last else None) or "live"
    ev.status = previous if previous != "closed" else "live"
    events.record(db, ev.id, "evaluation_reopened", actor, status=ev.status)
    db.flush()
    return {"status": ev.status}


# ----------------------------
# Reminder settings
# ----------------------------

def update_settings(db: Session, ev: Evaluation, changes: Dict[str, Any], actor: str) -> Dict[str, Any]:
    clean = sched.validate_settings(changes)
    before = settings_of(ev)
    ev.reminder_settings = {**(ev.reminder_settings or {}), **clean}
    after = settings_of(ev)
    changed = {k: after[k] for k in after if after[k] != before[k]}
    if changed:
        events.record(db, ev.id, "reminder_settings_changed", actor, **changed)
    db.flush()
    return after


def settings_view(db: Session, ev: Evaluation, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The settings, the schedule for this evaluation in plain dates, and today's dry run."""
    now = now or _now()
    settings = settings_of(ev)
    rows = load_rows(db, ev)
    firsts = sorted(r.first_sent_at.date() for r in rows if r.first_sent_at)
    sent_on = firsts[0] if firsts else now.date()
    slots = sched.schedule(settings, sent_on, ev.deadline)
    return {
        "settings": settings,
        "defaults": sched.DEFAULT_SETTINGS,
        "schedule": {
            "based_on": sent_on.isoformat(), "based_on_invites": bool(firsts),
            "slots": [{"on": s.on.isoformat(), "final": s.final} for s in slots],
        },
        "dry_run": due_list(db, ev, now, settings={**settings, "enabled": True}),
    }

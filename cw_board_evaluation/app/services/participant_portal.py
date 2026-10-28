"""
app.services.participant_portal
-------------------------------
What a participant sees and does for an evaluation that uses assembled
question sets: one assignment (one link) per participant, one form built from
their approved set, answers saved as they go, and one submission.

- Assignment: exactly one AssessmentAssignment of type ASSEMBLED per participant,
  created (or reused) when their approved set is invited or sent links. Its
  token (32 random bytes, URL-safe) is the only thing in their link.
- Opening the form for the first time locks the set (no more consultant edits).
- Answers are one Response per question: `answer` holds the full answer,
  `score` the rating (or 1/0 for yes/no) so existing analytics keep working,
  and `evaluation_subject_id` the person, committee or board it is about.
- Confirm items: "Correct" or "Needs updating" with an optional correction. A
  correction never changes the confirmed fact; on submission it becomes a
  PROPOSED fact with origin "participant" for a consultant to review.

The form never exposes bank codes, tags, rule reasons, AI wording or other
internal fields: only the final text and what's needed to answer it.
"""

from __future__ import annotations

import os
import secrets
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AssessmentAssignment,
    BoardMember,
    BoardMemberFact,
    Evaluation,
    EvaluationSubject,
    Organisation,
    OrganisationFact,
    Participant,
    ParticipantQuestionSet,
    Question,
    QuestionBankItem,
    Response,
)
from app.domain.question_bank import GRID_ITEM_PREFIX
from app.domain.question_rules import fact_scope
from app.services import participant_events as events
from app.services.question_assembly import SECTIONS, set_metrics
from app.services.question_sets import lock_set, question_set, set_questions
from app.util.portal_urls import assembled_form_url

ASSEMBLED = "ASSEMBLED"

SECTION_TITLES = {
    "board": "Board", "committees": "Committees", "colleagues": "Colleagues", "yourself": "About you",
    "confirm": "Confirm details", "additional": "Additional",
}

MAX_TEXT = 5000
MAX_CORRECTION = 2000


class PortalError(Exception):
    """A request the participant can't make now. `message` is safe to show them."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class AnswerError(ValueError):
    """Answers that don't fit their questions: [{"question_id", "message"}]."""

    def __init__(self, errors: List[Dict[str, str]]):
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ----------------------------
# Evaluation settings
# ----------------------------

def consultancy_name() -> str:
    return (os.getenv("CONSULTANCY_NAME") or "Crest & Waterfalls").strip()


def default_notice() -> str:
    # Neutral on purpose: whether answers are anonymous isn't decided, so promise nothing about it
    return f"Your answers will be used by {consultancy_name()} to prepare the board evaluation report."


def participant_notice(ev: Evaluation) -> str:
    return (ev.participant_notice or "").strip() or default_notice()


def uses_assembled_sets(db: Session, evaluation_id: str) -> bool:
    """Evaluations with any assembled set use one form per participant; the rest are legacy."""
    return db.execute(select(ParticipantQuestionSet.id).where(
        ParticipantQuestionSet.evaluation_id == evaluation_id).limit(1)).first() is not None


def evaluation_title(ev: Evaluation) -> str:
    return (ev.name or "").strip() or f"{ev.year} Board Evaluation"


def organisation_name(db: Session, ev: Evaluation) -> str:
    org = db.get(Organisation, ev.organisation_id) if ev.organisation_id else None
    return org.name if org else ev.tenant_name


# ----------------------------
# Assignment and token
# ----------------------------

def new_token(db: Session) -> str:
    """32 random bytes, URL-safe (43 characters), unique across assignment and hub tokens."""
    for _ in range(8):
        token = secrets.token_urlsafe(32)
        taken = db.execute(select(AssessmentAssignment.id).where(AssessmentAssignment.access_token == token)).first() \
            or db.execute(select(Participant.id).where(Participant.access_token == token)).first()
        if not taken:
            return token
    raise RuntimeError("Could not generate a unique link token.")


def form_assignment(db: Session, participant_id) -> Optional[AssessmentAssignment]:
    return db.execute(select(AssessmentAssignment).where(
        AssessmentAssignment.respondent_participant_id == participant_id,
        AssessmentAssignment.assignment_type == ASSEMBLED)).scalars().first()


def ensure_form_assignment(db: Session, participant: Participant, pset: ParticipantQuestionSet) -> AssessmentAssignment:
    """The participant's one form assignment, created on first invite and reused after that."""
    a = form_assignment(db, participant.id)
    if a is None:
        a = AssessmentAssignment(
            evaluation_id=participant.evaluation_id, respondent_participant_id=participant.id,
            assignment_type=ASSEMBLED, instrument_template_code=f"P:{participant.id}", instrument_version=1,
            access_token=new_token(db), token_created_at=_now(), status="invited", question_set_id=pset.id,
        )
        db.add(a)
    else:
        a.question_set_id = pset.id
        if not (a.access_token or "").strip():
            a.access_token, a.token_created_at = new_token(db), _now()
    db.flush()
    return a


def form_link(a: AssessmentAssignment) -> str:
    return assembled_form_url(a.access_token or "")


def send_form_link(db: Session, ev: Evaluation, participant: Participant, *, only_pending: bool = False,
                   actor: str = "consultant", event_type: str = "invite_sent", **detail: Any) -> Dict[str, Any]:
    """
    Email one participant their form link (the caller has already applied the invite gate).
    Returns {"sent", "error", "skipped", "url"}; records when the email went, and an event:
    `event_type` ("invite_sent" or "link_resent") on success, "email_failed" with the error otherwise.
    """
    from app.services.email_service import send_form_invite_email  # tests patch it here

    pset = question_set(db, participant.id)
    a = ensure_form_assignment(db, participant, pset)
    url = form_link(a)
    if only_pending and a.submitted_at:
        return {"sent": False, "error": None, "skipped": "already_submitted", "url": url}
    minutes = set_metrics(db, pset)["estimated_minutes"]
    ok, err = send_form_invite_email(
        to_email=participant.email, full_name=participant.full_name, form_url=url,
        organisation=organisation_name(db, ev), evaluation_name=evaluation_title(ev), consultancy=consultancy_name(),
        estimated_minutes=minutes, deadline=ev.deadline, notice=participant_notice(ev),
    )
    if ok:
        a.email_sent_at = _now()
        events.record(db, ev.id, event_type, actor, participant_id=participant.id, assignment_id=a.id, **detail)
    else:
        events.record(db, ev.id, events.EMAIL_FAILED, actor, participant_id=participant.id, assignment_id=a.id,
                      kind=event_type, error=events.short_error(err), **detail)
    db.flush()
    return {"sent": bool(ok), "error": err, "skipped": None, "url": url}


# ----------------------------
# Resolving a link
# ----------------------------

INVALID_LINK = ("This link isn't valid. Check you've used the full link from your email, "
                "or ask your consultant for a new one.")


def resolve(db: Session, token: str, *, for_change: bool = False
            ) -> Tuple[AssessmentAssignment, Evaluation, Participant, ParticipantQuestionSet]:
    """
    The assignment, evaluation, participant and set behind a form link, or a PortalError.
    for_change: saving or submitting (refused once submitted, closed or past the deadline).
    """
    t = (token or "").strip()
    a = db.execute(select(AssessmentAssignment).where(AssessmentAssignment.access_token == t)).scalars().first() \
        if t else None
    if a is None or a.assignment_type != ASSEMBLED:
        raise PortalError(404, "invalid_link", INVALID_LINK)
    ev = db.get(Evaluation, a.evaluation_id)
    participant = db.get(Participant, a.respondent_participant_id)
    pset = question_set(db, a.respondent_participant_id)
    if ev is None or participant is None or pset is None:
        raise PortalError(404, "invalid_link", INVALID_LINK)
    who = consultancy_name()
    if not a.submitted_at:
        if ev.status == "closed":
            raise PortalError(410, "closed", f"This evaluation has closed. If you still need to respond, contact {who}.")
        if ev.deadline and date.today() > ev.deadline:
            raise PortalError(410, "expired", f"The deadline for this evaluation ({ev.deadline.strftime('%d %B %Y').lstrip('0')}) "
                                              f"has passed. If you still need to respond, contact {who}.")
    if pset.status == "draft":
        raise PortalError(409, "being_updated", "Your questions are being updated. Please try again later; "
                                                "any answers you've saved are kept.")
    if for_change and a.submitted_at:
        raise PortalError(409, "submitted", "You've already submitted your answers, so they can't be changed. "
                                            f"Contact {who} if something needs correcting.")
    return a, ev, participant, pset


# ----------------------------
# The form
# ----------------------------

def form_questions(db: Session, participant_id) -> List[Question]:
    """The questions the participant answers: approved (or, once opened, locked) ones, in order."""
    return [q for q in set_questions(db, participant_id) if q.status in ("approved", "locked")]


def _bank_items(db: Session, questions: List[Question]) -> Dict[Any, QuestionBankItem]:
    ids = {q.bank_item_id for q in questions if q.bank_item_id}
    if not ids:
        return {}
    return {i.id: i for i in db.execute(select(QuestionBankItem).where(QuestionBankItem.id.in_(ids))).scalars().all()}


def is_required(q: Question, item: Optional[QuestionBankItem]) -> bool:
    """Free-text comments and bank items marked optional can be left blank; everything else needs an answer."""
    if q.section == "confirm":
        return True
    if q.answer_type == "comment":
        return False
    return not (item is not None and item.priority == "optional")


def _is_grid(q: Question, item: Optional[QuestionBankItem]) -> bool:
    return (q.section == "colleagues" and q.answer_type == "rating" and item is not None
            and item.code.startswith(GRID_ITEM_PREFIX))


def _about(subject: Optional[EvaluationSubject], participant_id) -> Optional[str]:
    """Who or what a question is about, by name; None for the board as a whole and for the participant themselves."""
    if subject is None or subject.subject_type_code == "BOARD":
        return None
    if subject.participant_id and str(subject.participant_id) == str(participant_id) \
            and subject.subject_type_code != "COMPANY_SECRETARY":
        return None
    return subject.label.split(" · ")[-1]  # drop the internal display code ("P001 · ...")


def _scale(q: Question) -> Optional[Dict[str, Any]]:
    if q.answer_type != "rating":
        return None
    s = q.scale or {"min": 1, "max": 5, "labels": {}}
    labels = s.get("labels") or {}
    lo, hi = int(s.get("min", 1)), int(s.get("max", 5))
    return {"min": lo, "max": hi, "dont_know": bool(s.get("dont_know")),
            "points": [{"value": v, "label": labels.get(str(v))} for v in range(lo, hi + 1)]}


def answer_value(r: Response, q: Question) -> Any:
    """A stored response in the shape the form sends and receives."""
    a = r.answer or {}
    if q.section == "confirm":
        return {"status": a.get("confirm"), "correction": a.get("correction") or ""}
    if q.answer_type == "rating":
        return "dont_know" if a.get("dont_know") else r.score
    if q.answer_type == "yesno":
        return a.get("value") or ({1: "yes", 0: "no"}.get(r.score))
    if q.answer_type == "comment":
        return r.comment
    if q.answer_type == "single_select":
        return a.get("value")
    if q.answer_type == "multi_select":
        return a.get("values") or []
    return None


def _responses(db: Session, a: AssessmentAssignment) -> Dict[str, Response]:
    return {str(r.question_id): r for r in db.execute(select(Response).where(Response.assignment_id == a.id)).scalars()}


def _visible(questions: List[Question], answers: Dict[str, Any]) -> Dict[str, bool]:
    """Follow-ups show only when their parent's answer matches show_if (and the parent itself is shown)."""
    by_id = {str(q.id): q for q in questions}
    out: Dict[str, bool] = {}

    def shown(q: Question, depth: int = 0) -> bool:
        key = str(q.id)
        if key in out:
            return out[key]
        if not q.depends_on_question_id or depth > 10:
            out[key] = True
            return True
        parent = by_id.get(str(q.depends_on_question_id))
        want = (q.show_if or {}).get("answer")
        out[key] = bool(parent is not None and shown(parent, depth + 1) and answers.get(str(parent.id)) == want)
        return out[key]

    for q in questions:
        shown(q)
    return out


def unanswered_required(questions: List[Question], items, answers: Dict[str, Any]) -> List[Question]:
    """Required questions that are shown (follow-ups only when their condition is met) and not answered yet."""
    visible = _visible(questions, answers)
    return [q for q in questions if visible[str(q.id)] and is_required(q, items.get(q.bank_item_id))
            and not _has_answer(q, answers.get(str(q.id)))]


def progress_of(questions: List[Question], items, answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Answered and required counts over the visible questions. The submit check, the form and
    consultant tracking all use this, so their numbers always agree.
    """
    visible = _visible(questions, answers)
    shown = [q for q in questions if visible[str(q.id)]]
    required = [q for q in shown if is_required(q, items.get(q.bank_item_id))]
    return {
        "questions": len(shown),
        "answered": sum(1 for q in shown if _has_answer(q, answers.get(str(q.id)))),
        "required": len(required),
        "required_answered": len(required) - len(unanswered_required(questions, items, answers)),
    }


def _has_answer(q: Question, v: Any) -> bool:
    if v is None:
        return False
    if q.section == "confirm":
        return isinstance(v, dict) and v.get("status") in ("correct", "needs_updating")
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return bool(v)
    return True


def form_status(a: AssessmentAssignment) -> str:
    if a.submitted_at:
        return "submitted"
    return "in_progress" if a.last_activity_at else "not_started"


def build_form(db: Session, a: AssessmentAssignment, ev: Evaluation, participant: Participant,
               pset: ParticipantQuestionSet) -> Dict[str, Any]:
    questions = form_questions(db, participant.id)
    items = _bank_items(db, questions)
    subjects = {s.id: s for s in db.execute(select(EvaluationSubject).where(
        EvaluationSubject.evaluation_id == ev.id)).scalars().all()}
    responses = _responses(db, a)
    by_id = {str(q.id): q for q in questions}
    answers = {qid: answer_value(r, by_id[qid]) for qid, r in responses.items() if qid in by_id}

    def question_out(q: Question) -> Dict[str, Any]:
        out = {
            "id": str(q.id), "text": q.text, "answer_type": q.answer_type,
            "options": q.options if q.answer_type in ("single_select", "multi_select") else None,
            "scale": _scale(q), "required": is_required(q, items.get(q.bank_item_id)),
            "about": _about(subjects.get(q.evaluation_subject_id), participant.id),
            "follows": ({"question_id": str(q.depends_on_question_id), "answer": (q.show_if or {}).get("answer")}
                        if q.depends_on_question_id else None),
            "confirm": None,
        }
        if q.section == "confirm" and q.confirm_value:
            out["confirm"] = {"label": q.confirm_value.get("known_from_label"),
                              "value": q.confirm_value.get("value_text")}
        return out

    sections = []
    for key in SECTIONS:
        rows = [q for q in questions if q.section == key]
        if not rows:
            continue
        blocks: List[Dict[str, Any]] = []
        grid: Optional[Dict[str, Any]] = None
        for q in rows:
            item = items.get(q.bank_item_id)
            if _is_grid(q, item):
                if grid is None:  # the core peer grid is one block, placed where its first cell was
                    grid = {"kind": "grid", "id": "peer-grid", "statements": [], "colleagues": [],
                            "scale": _scale(q), "required": is_required(q, item)}
                    blocks.append(grid)
                about = subjects.get(q.evaluation_subject_id)
                col = str(q.evaluation_subject_id)
                if not any(c["id"] == col for c in grid["colleagues"]):
                    grid["colleagues"].append({"id": col, "name": _about(about, participant.id) or "Colleague"})
                row = next((s for s in grid["statements"] if s["key"] == item.code), None)
                if row is None:
                    row = {"key": item.code, "text": q.bank_text or q.text, "cells": {}}
                    grid["statements"].append(row)
                row["cells"][col] = str(q.id)
            else:
                blocks.append({"kind": "question", **question_out(q)})
        if grid is not None:  # statement keys are bank codes: number them instead
            for n, s in enumerate(grid["statements"], start=1):
                s["key"] = f"s{n}"
        sections.append({"key": key, "title": SECTION_TITLES[key], "blocks": blocks})

    return {
        "evaluation": {
            "name": evaluation_title(ev), "organisation": organisation_name(db, ev),
            "deadline": ev.deadline.isoformat() if ev.deadline else None,
            "notice": participant_notice(ev), "consultancy": consultancy_name(),
        },
        "participant": {"name": participant.full_name},
        "estimated_minutes": set_metrics(db, pset)["estimated_minutes"],
        "status": form_status(a),
        "opened_at": _iso(a.opened_at), "submitted_at": _iso(a.submitted_at),
        "sections": sections,
        "answers": answers,
        "progress": progress_of(questions, items, answers),
    }


def open_form(db: Session, token: str) -> Dict[str, Any]:
    """Load the form; the first open locks the set and records when it was opened."""
    a, ev, participant, pset = resolve(db, token)
    if pset.status == "approved":
        lock_set(db, pset, by="participant")
    if a.opened_at is None:
        a.opened_at = _now()
        events.record(db, ev.id, "opened", "participant", participant_id=participant.id, assignment_id=a.id)
    db.flush()
    return build_form(db, a, ev, participant, pset)


# ----------------------------
# Answers
# ----------------------------

def _clean(q: Question, value: Any) -> Tuple[Optional[int], Optional[str], Optional[Dict[str, Any]]]:
    """(score, comment, answer) for a valid value, or ValueError with a message for the participant."""
    if q.section == "confirm":
        if not isinstance(value, dict) or value.get("status") not in ("correct", "needs_updating"):
            raise ValueError("Choose Correct or Needs updating.")
        correction = str(value.get("correction") or "").strip()
        if len(correction) > MAX_CORRECTION:
            raise ValueError(f"Keep the correction under {MAX_CORRECTION} characters.")
        if value["status"] == "correct":
            correction = ""
        return None, None, {"confirm": value["status"], "correction": correction or None}
    at = q.answer_type
    if at == "rating":
        s = _scale(q)
        if value == "dont_know" and s["dont_know"]:
            return None, None, {"dont_know": True}
        if isinstance(value, bool) or not isinstance(value, int) or not s["min"] <= value <= s["max"]:
            raise ValueError(f"Choose a rating from {s['min']} to {s['max']}.")
        return value, None, {"value": value}
    if at == "yesno":
        if value not in ("yes", "no"):
            raise ValueError("Choose Yes or No.")
        return (1 if value == "yes" else 0), None, {"value": value}
    if at == "comment":
        if not isinstance(value, str):
            raise ValueError("Answer in words.")
        if len(value) > MAX_TEXT:
            raise ValueError(f"Keep your answer under {MAX_TEXT} characters.")
        return None, value, None
    options = q.options or []
    if at == "single_select":
        if value not in options:
            raise ValueError("Choose one of the options.")
        return None, None, {"value": value}
    if at == "multi_select":
        if not isinstance(value, list) or not value or any(v not in options for v in value):
            raise ValueError("Choose one or more of the options.")
        return None, None, {"values": [o for o in options if o in value]}
    raise ValueError("This question can't be answered here.")


def _empty(q: Question, value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip() and q.section != "confirm") \
        or (isinstance(value, list) and not value)


def save_answers(db: Session, token: str, answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Upsert answers ({"question_id", "value"}); an empty value clears the answer. All or nothing:
    any invalid answer, or a question not in this participant's form, rejects the whole batch.
    """
    a, ev, participant, pset = resolve(db, token, for_change=True)
    questions = {str(q.id): q for q in form_questions(db, participant.id)}
    errors: List[Dict[str, str]] = []
    cleaned = []
    for ans in answers:
        qid = str(ans.get("question_id") or "")
        q = questions.get(qid)
        if q is None:
            errors.append({"question_id": qid, "message": "This question isn't part of your form."})
            continue
        value = ans.get("value")
        if _empty(q, value):
            cleaned.append((q, None))
            continue
        try:
            cleaned.append((q, _clean(q, value)))
        except ValueError as e:
            errors.append({"question_id": qid, "message": str(e)})
    if errors:
        raise AnswerError(errors)

    existing = _responses(db, a)
    first = not existing and any(parts is not None for _, parts in cleaned)
    now = _now()
    for q, parts in cleaned:
        r = existing.get(str(q.id))
        if parts is None:
            if r is not None:
                db.delete(r)
            continue
        score, comment, answer = parts
        if r is None:
            r = Response(evaluation_id=ev.id, participant_id=participant.id, assignment_id=a.id, question_id=q.id,
                         evaluation_subject_id=q.evaluation_subject_id)
            db.add(r)
            existing[str(q.id)] = r
        r.score, r.comment, r.answer, r.updated_at = score, comment, answer, now
    a.last_activity_at = now
    if first:
        events.record(db, ev.id, "first_answer", "participant", participant_id=participant.id, assignment_id=a.id)
    db.flush()
    rows = form_questions(db, participant.id)
    current = {qid: answer_value(r, questions[qid]) for qid, r in _responses(db, a).items() if qid in questions}
    return {"saved": len(cleaned), "saved_at": now.isoformat(),
            "progress": progress_of(rows, _bank_items(db, rows), current)}


# ----------------------------
# Submission
# ----------------------------

def missing_required(db: Session, a: AssessmentAssignment, participant: Participant) -> List[Dict[str, Any]]:
    questions = form_questions(db, participant.id)
    items = _bank_items(db, questions)
    by_id = {str(q.id): q for q in questions}
    answers = {qid: answer_value(r, by_id[qid]) for qid, r in _responses(db, a).items() if qid in by_id}
    subjects = {s.id: s for s in db.execute(select(EvaluationSubject).where(
        EvaluationSubject.evaluation_id == participant.evaluation_id)).scalars().all()}
    return [{"question_id": str(q.id), "section": q.section, "text": q.text,
             "about": _about(subjects.get(q.evaluation_subject_id), participant.id)}
            for q in unanswered_required(questions, items, answers)]


def submit(db: Session, token: str) -> Dict[str, Any]:
    """Submit when every required visible question is answered; otherwise return what's missing."""
    a, ev, participant, pset = resolve(db, token, for_change=True)
    missing = missing_required(db, a, participant)
    if missing:
        return {"submitted": False, "missing": missing}
    questions = form_questions(db, participant.id)
    by_id = {str(q.id): q for q in questions}
    responses = _responses(db, a)
    answers = {qid: answer_value(r, by_id[qid]) for qid, r in responses.items() if qid in by_id}
    visible = _visible(questions, answers)
    proposals = []
    for qid, r in responses.items():
        q = by_id.get(qid)
        if q is None or not visible.get(qid):  # answers to follow-ups that are no longer shown aren't kept
            db.delete(r)
            continue
        if q.section == "confirm" and (r.answer or {}).get("confirm") == "needs_updating" \
                and not (r.answer or {}).get("proposed"):  # already proposed before the form was reopened
            fact = propose_correction(db, ev, participant, q, (r.answer or {}).get("correction"))
            if fact is not None:
                proposals.append(str(fact.id))
                r.answer = {**r.answer, "proposed": True}
    now = _now()
    a.submitted_at, a.responded_at, a.status, a.last_activity_at = now, now, "responded", now
    participant.status, participant.responded_at = "responded", now
    events.record(db, ev.id, "submitted", "participant", participant_id=participant.id, assignment_id=a.id,
                  proposals=len(proposals) or None)
    db.flush()
    return {"submitted": True, "submitted_at": now.isoformat(), "missing": [], "proposals": len(proposals)}


def propose_correction(db: Session, ev: Evaluation, participant: Participant, q: Question,
                       correction: Optional[str]):
    """
    A PROPOSED fact (origin "participant") with the participant's correction. The confirmed
    fact is never touched; a consultant confirms (with the right value) or rejects it.
    """
    stored = q.confirm_value or {}
    full_key = stored.get("known_from") or ""
    key = full_key.split(".")[0]
    if not key:
        return None
    who = participant.full_name or "The participant"
    text = (correction or "").strip()
    note = (f'{who} said the stored {(stored.get("known_from_label") or key).lower()} ("{stored.get("value_text")}") '
            f'needs updating, answering "{q.text}".' + ("" if text else " They didn't say what it should be."))
    common = dict(key=key, value=text or None, source="client", status="proposed", origin="participant", note=note)
    if fact_scope(full_key) == "org":
        if not ev.organisation_id:
            return None
        fact = OrganisationFact(organisation_id=ev.organisation_id, **common)
    else:
        subject = db.get(EvaluationSubject, q.evaluation_subject_id) if q.evaluation_subject_id else None
        person = db.get(Participant, subject.participant_id) if subject is not None and subject.participant_id else None
        member_id = (person or participant).board_member_id
        if member_id is None or db.get(BoardMember, member_id) is None:
            return None
        fact = BoardMemberFact(board_member_id=member_id, **common)
    db.add(fact)
    db.flush()
    return fact

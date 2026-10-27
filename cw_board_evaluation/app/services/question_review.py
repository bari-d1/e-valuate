"""
app.services.question_review
----------------------------
The consultant's review of assembled question sets, on top of
app.services.question_sets: tag edits, removing and restoring, adding from the
bank or writing a question, reordering, bulk approval, and the cross-participant
views (the evaluation overview and every question about one subject).

Every change needs a draft set, keeps the question's subject and tags, and is
recorded as a QuestionSetEvent (who, when, what changed). Callers refresh the
set's live metrics afterwards (question_assembly.refresh_summary).
"""

from __future__ import annotations

import difflib
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BoardMember,
    CommitteeMembership,
    EvaluationSubject,
    Evaluation,
    EvidenceSource,
    OrgCommittee,
    Participant,
    ParticipantQuestionSet,
    Question,
    QuestionBankItem,
    QuestionSubjectType,
    Theme,
)
from app.domain.board_member_profile import governance_role_from_participant_role
from app.domain.question_bank import ANSWER_TYPES, SCALES
from app.services import question_bank as bank
from app.services.board_members import READY, participant_readiness
from app.services.question_assembly import (
    MIN_RATERS,
    SECTIONS,
    SetConflict,
    _ensure_subject,
    active_questions,
    drafts_allowed,
    live_rater_warnings,
    refresh_summary,
    renumber,
    set_metrics,
    template_code_for,
)
from app.services.question_selection import (
    ROLE_LABELS,
    _person_subject,
    _subject_ref,
    build_selection_context,
    fill_for_subject,
    item_spec,
)
from app.services.question_sets import (
    _require_draft,
    approve_set,
    log_event,
    question_set,
    require_draft_set,
    set_questions,
)

LONG_SET_MINUTES = 45
# Wordings of one bank item for different people this similar or less are flagged as worded very differently
WORDING_SIMILARITY_FLAG = 0.75
FOLLOWS_REMOVED = "Follows a removed question."


# ----------------------------
# Subjects
# ----------------------------

def _base_subjects(base: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every subject a question in this evaluation can be about, in selection's shape."""
    out = [{"kind": "board", "type": "BOARD", "label": "The board", "facts": {}}]
    out.extend(base["committees"])
    for person in base["people"]:
        s = _person_subject(person)
        if s:
            out.append(s)
    return out


def subject_options(db: Session, ev: Evaluation, base: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The subjects a consultant can pick for a question (rows created as needed), board first."""
    base = base or build_selection_context(db, ev)
    secretary = next((p["participant_id"] for p in base["people"] if p.get("role") == "company_secretary"), None)
    cache: Dict[str, EvaluationSubject] = {}
    out = []
    for s in _base_subjects(base):
        ref = _subject_ref(s)
        row = _ensure_subject(db, ev, ref, cache, secretary)
        out.append({"id": str(row.id), "type": row.subject_type_code, "kind": ref["kind"], "label": ref["label"],
                    "participant_id": ref.get("participant_id")})
    return out


def _subject_for(db: Session, ev: Evaluation, subject_id: str) -> EvaluationSubject:
    try:
        row = db.get(EvaluationSubject, uuid.UUID(str(subject_id)))
    except ValueError:
        row = None
    if row is None or row.evaluation_id != ev.id:
        raise ValueError("Choose a subject from this evaluation.")
    return row


def _selection_subject(base: Dict[str, Any], row: EvaluationSubject) -> Dict[str, Any]:
    """The selection-shaped subject (with its facts) for a stored subject row."""
    if row.subject_type_code == "BOARD":
        return {"kind": "board", "type": "BOARD", "label": "The board", "facts": {}}
    if row.committee_name:
        c = next((c for c in base["committees"] if c["label"] == row.committee_name), None)
        if c:
            return c
    if row.participant_id:
        person = next((p for p in base["people"] if p["participant_id"] == str(row.participant_id)), None)
        s = _person_subject(person) if person else None
        if s:
            return s
    return {"kind": "function", "type": row.subject_type_code, "label": row.label, "facts": {}}


def _section_for(row: EvaluationSubject, participant_id) -> str:
    if row.committee_name:
        return "committees"
    if row.participant_id is None or row.subject_type_code == "BOARD":
        return "board"
    return "yourself" if str(row.participant_id) == str(participant_id) else "colleagues"


def _check_tags(db: Session, theme_code: Optional[str], evidence_source_code: Optional[str]) -> None:
    if theme_code is not None and db.get(Theme, theme_code) is None:
        raise ValueError(f"Unknown theme {theme_code!r}.")
    if evidence_source_code is not None and db.get(EvidenceSource, evidence_source_code) is None:
        raise ValueError(f"Unknown evidence source {evidence_source_code!r}.")


def _set_for(db: Session, participant_id) -> ParticipantQuestionSet:
    return require_draft_set(question_set(db, participant_id))


# ----------------------------
# Tags
# ----------------------------

def edit_tags(db: Session, ev: Evaluation, q: Question, by: str, changes: Dict[str, Any]) -> Question:
    """
    changes may hold subject_id, theme_code, evidence_source_code. A question always keeps a subject:
    an empty subject is refused. A bank question's subject must be of a type the bank item covers.
    """
    pset = _require_draft(db, q)
    before = {"subject_id": str(q.evaluation_subject_id) if q.evaluation_subject_id else None,
              "theme_code": q.theme_code, "evidence_source_code": q.evidence_source_code}
    if "subject_id" in changes:
        if not changes["subject_id"]:
            raise ValueError("A question must keep a subject: choose another subject instead of removing it.")
        row = _subject_for(db, ev, changes["subject_id"])
        if q.bank_item_id:
            item = db.get(QuestionBankItem, q.bank_item_id)
            if item and row.subject_type_code not in item.subject_type_codes:
                raise ValueError(f"{item.code} is about {', '.join(item.subject_type_codes)}; "
                                 f"{row.label} doesn't fit it.")
        q.evaluation_subject_id = row.id
        q.subject_type_links = [QuestionSubjectType(subject_type_code=row.subject_type_code)]
        if q.section not in ("confirm", "additional"):
            q.section = _section_for(row, q.participant_id)
    for key in ("theme_code", "evidence_source_code"):
        if key in changes and not changes[key]:
            raise ValueError("Every question needs a theme and an evidence source.")
    _check_tags(db, changes.get("theme_code"), changes.get("evidence_source_code"))
    if changes.get("theme_code"):
        q.theme_code = changes["theme_code"]
        q.dimension = db.get(Theme, q.theme_code).name
    if changes.get("evidence_source_code"):
        q.evidence_source_code = changes["evidence_source_code"]
    after = {"subject_id": str(q.evaluation_subject_id), "theme_code": q.theme_code,
             "evidence_source_code": q.evidence_source_code}
    if after != before:
        renumber(set_questions(db, q.participant_id))
        log_event(db, pset, "edit_tags", by, q=q, before=before, after=after)
    return q


# ----------------------------
# Remove and restore
# ----------------------------

def remove_question(db: Session, q: Question, by: str, reason: Optional[str] = None) -> Question:
    """Leave a question out of the participant's set; it stays in the database for audit. Follow-ups go with it."""
    pset = _require_draft(db, q)
    q.status, q.removed_reason = "removed", (reason or "").strip() or None
    children = [c for c in set_questions(db, q.participant_id) if c.depends_on_question_id == q.id and c.status != "removed"]
    for c in children:
        c.status, c.removed_reason = "removed", FOLLOWS_REMOVED
    log_event(db, pset, "remove", by, q=q, reason=q.removed_reason, text=q.text,
              follow_ups=[str(c.id) for c in children] or None)
    return q


def restore_question(db: Session, q: Question, by: str) -> Question:
    pset = _require_draft(db, q, allow_removed=True)
    if q.status != "removed":
        raise SetConflict("This question isn't removed.")
    if q.depends_on_question_id:
        parent = db.get(Question, q.depends_on_question_id)
        if parent is not None and parent.status == "removed":
            raise SetConflict("It follows a removed question; restore that one first.")
    q.status, q.removed_reason = "draft", None
    children = [c for c in set_questions(db, q.participant_id)
                if c.depends_on_question_id == q.id and c.status == "removed" and c.removed_reason == FOLLOWS_REMOVED]
    for c in children:
        c.status, c.removed_reason = "draft", None
    log_event(db, pset, "restore", by, q=q, text=q.text, follow_ups=[str(c.id) for c in children] or None)
    return q


# ----------------------------
# Add
# ----------------------------

def _person(base: Dict[str, Any], participant_id) -> Dict[str, Any]:
    person = next((p for p in base["people"] if p["participant_id"] == str(participant_id)), None)
    if person is None:
        raise ValueError("Participant not found in this evaluation.")
    return person


def _place_last_in_section(db: Session, q: Question) -> None:
    rows = set_questions(db, q.participant_id)
    same = [r.sort_order or 0 for r in rows if r.section == q.section and r.id != q.id]
    q.sort_order = (max(same) if same else (SECTIONS.index(q.section) + 1) * 100000) + 5
    renumber(rows if q in rows else rows + [q])


def search_bank(db: Session, text: str = "", subject_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Approved bank items (drafts too when ASSEMBLY_ALLOW_DRAFTS is set) matching code or wording."""
    statuses = ("approved", "draft") if drafts_allowed() else ("approved",)
    latest: Dict[str, QuestionBankItem] = {}
    for i in bank.list_items(db):
        if i.status in statuses and (i.code not in latest or i.version > latest[i.code].version):
            latest[i.code] = i
    t = (text or "").strip().lower()
    out = []
    for i in sorted(latest.values(), key=lambda i: (i.sort_order or 0, i.code)):
        if t and t not in i.code.lower() and t not in i.text.lower():
            continue
        if subject_type and subject_type not in i.subject_type_codes:
            continue
        out.append({"id": str(i.id), "code": i.code, "version": i.version, "status": i.status, "text": i.text,
                    "answer_type": i.answer_type, "subject_types": i.subject_type_codes, "theme_code": i.theme_code,
                    "evidence_source_code": i.evidence_source_code, "placeholders": i.placeholders or []})
        if len(out) >= limit:
            break
    return out


def add_from_bank(db: Session, ev: Evaluation, participant: Participant, item_id: str, subject_id: str,
                  by: str) -> Question:
    pset = _set_for(db, participant.id)
    try:
        item = db.get(QuestionBankItem, uuid.UUID(str(item_id)))
    except ValueError:
        item = None
    if item is None:
        raise ValueError("Bank item not found.")
    if not (item.status == "approved" or (item.status == "draft" and drafts_allowed())):
        raise ValueError(f"{item.code} v{item.version} is {item.status}; only approved bank items can be added.")
    row = _subject_for(db, ev, subject_id)
    if row.subject_type_code not in item.subject_type_codes:
        raise ValueError(f"{item.code} is about {', '.join(item.subject_type_codes)}; {row.label} doesn't fit it.")
    for existing in set_questions(db, participant.id):
        if existing.bank_item_id and str(existing.evaluation_subject_id) == str(row.id):
            other = db.get(QuestionBankItem, existing.bank_item_id)
            if other and other.code == item.code:
                if existing.status == "removed":
                    raise SetConflict(f"{item.code} about {row.label} was removed from this set; restore it instead.")
                raise SetConflict(f"{item.code} about {row.label} is already in this set.")
    base = build_selection_context(db, ev)
    filled = fill_for_subject(item_spec(item), base, _person(base, participant.id), _selection_subject(base, row))
    if filled["missing"]:
        raise ValueError(f"The wording needs {', '.join(filled['missing'])}, which isn't confirmed for {row.label}.")
    theme = db.get(Theme, item.theme_code)
    q = Question(
        template_code=template_code_for(participant.id), version=1, dimension=theme.name if theme else item.theme_code,
        text=filled["text"], answer_type=item.answer_type, weight=max(0, int(round(item.weight or 1))), active=1,
        theme_code=item.theme_code, evidence_source_code=item.evidence_source_code, evaluation_id=ev.id,
        participant_id=participant.id, bank_item_id=item.id, bank_item_version=item.version,
        evaluation_subject_id=row.id, section=_section_for(row, participant.id), status="draft", text_source="bank",
        bank_text=filled["text"], options=filled["options"], scale=item.scale, added_by=by or "consultant",
        selection_reason=f"Added by {by or 'a consultant'} from the bank.",
    )
    q.subject_type_links = [QuestionSubjectType(subject_type_code=row.subject_type_code)]
    db.add(q)
    db.flush()
    _place_last_in_section(db, q)
    log_event(db, pset, "add_from_bank", by, q=q, code=item.code, version=item.version, subject=row.label, text=q.text)
    return q


def add_written(db: Session, ev: Evaluation, participant: Participant, by: str, *, text: str, answer_type: str,
                subject_id: Optional[str], theme_code: Optional[str], evidence_source_code: Optional[str],
                options: Optional[List[str]] = None) -> Question:
    """A question the consultant writes. Text, answer type, subject, theme and evidence source are all required."""
    pset = _set_for(db, participant.id)
    text = (text or "").strip()
    missing = [label for label, v in (("the question text", text), ("an answer type", answer_type),
                                      ("a subject", subject_id), ("a theme", theme_code),
                                      ("an evidence source", evidence_source_code)) if not v]
    if missing:
        raise ValueError("A written question needs " + ", ".join(missing) + ".")
    if answer_type not in ANSWER_TYPES:
        raise ValueError(f"Answer type must be one of {', '.join(ANSWER_TYPES)}.")
    opts = [o.strip() for o in (options or []) if o and o.strip()]
    if answer_type in ("single_select", "multi_select") and len(opts) < 2:
        raise ValueError("A choice question needs at least two options.")
    _check_tags(db, theme_code, evidence_source_code)
    row = _subject_for(db, ev, subject_id)
    q = Question(
        template_code=template_code_for(participant.id), version=1, dimension=db.get(Theme, theme_code).name,
        text=text, answer_type=answer_type, weight=1, active=1, theme_code=theme_code,
        evidence_source_code=evidence_source_code, evaluation_id=ev.id, participant_id=participant.id,
        evaluation_subject_id=row.id, section=_section_for(row, participant.id), status="draft",
        text_source="consultant_written", options=opts if answer_type in ("single_select", "multi_select") else None,
        scale=SCALES["quality_5"] if answer_type == "rating" else None, added_by=by or "consultant",
        selection_reason=f"Written by {by or 'a consultant'}.",
    )
    q.subject_type_links = [QuestionSubjectType(subject_type_code=row.subject_type_code)]
    db.add(q)
    db.flush()
    _place_last_in_section(db, q)
    log_event(db, pset, "add_written", by, q=q, text=text, answer_type=answer_type, subject=row.label,
              theme_code=theme_code, evidence_source_code=evidence_source_code)
    return q


# ----------------------------
# Order
# ----------------------------

def move_question(db: Session, q: Question, by: str, *, direction: Optional[str] = None,
                  position: Optional[int] = None) -> Question:
    """Move within its section: direction "up" | "down", or position (1 = first in the section)."""
    pset = _require_draft(db, q, allow_removed=True)
    rows = set_questions(db, q.participant_id)
    section = [r for r in rows if r.section == q.section]
    old = section.index(q)
    if direction in ("up", "down"):
        new = old - 1 if direction == "up" else old + 1
    elif position is not None:
        new = int(position) - 1
    else:
        raise ValueError("Give a direction (up or down) or a position.")
    new = max(0, min(len(section) - 1, new))
    if new == old:
        return q
    slots = sorted(r.sort_order or 0 for r in section)
    section.pop(old)
    section.insert(new, q)
    for r, slot in zip(section, slots):
        r.sort_order = slot
    renumber(rows)
    log_event(db, pset, "move", by, q=q, section=q.section, before=old + 1, after=new + 1)
    return q


# ----------------------------
# Bulk approval
# ----------------------------

def bulk_approve(db: Session, ev: Evaluation, participant_ids: List[str], by: str,
                 override_reason: Optional[str] = None) -> List[Dict[str, Any]]:
    """Approve several sets at once. One override reason covers every set in the batch that has gaps."""
    results = []
    for pid in participant_ids:
        try:
            p = db.get(Participant, uuid.UUID(str(pid)))
        except ValueError:
            p = None
        if p is None or p.evaluation_id != ev.id:
            results.append({"participant_id": str(pid), "outcome": "not_approved",
                            "reason": "Not a participant of this evaluation."})
            continue
        label = p.full_name or p.email
        pset = question_set(db, p.id)
        if pset is None:
            results.append({"participant_id": str(p.id), "label": label, "outcome": "not_approved",
                            "reason": "No question set has been assembled for them yet."})
            continue
        try:
            approve_set(db, pset, by, override_reason, batch=True)
            results.append({"participant_id": str(p.id), "label": label, "outcome": "approved",
                            "override_reason": pset.override_reason})
        except SetConflict as e:
            results.append({"participant_id": str(p.id), "label": label, "outcome": "not_approved", "reason": str(e)})
    return results


# ----------------------------
# Overview
# ----------------------------

def _committees_by_member(db: Session, member_ids: List[Any]) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    if not member_ids:
        return out
    for ms, c in db.execute(
        select(CommitteeMembership, OrgCommittee).join(OrgCommittee, OrgCommittee.id == CommitteeMembership.committee_id)
        .where(CommitteeMembership.board_member_id.in_(member_ids), CommitteeMembership.status == "confirmed",
               OrgCommittee.status == "confirmed")
    ).all():
        out.setdefault(str(ms.board_member_id), []).append({"name": c.name, "role": ms.membership_role})
    return out


def participant_header(db: Session, p: Participant) -> Dict[str, Any]:
    role = governance_role_from_participant_role(p.role)
    member = db.get(BoardMember, p.board_member_id) if p.board_member_id else None
    committees = _committees_by_member(db, [member.id]).get(str(member.id), []) if member else []
    return {"role_label": ROLE_LABELS.get(role or "", "Role not confirmed"),
            "display_code": member.display_code if member else None,
            "committees": sorted(committees, key=lambda c: c["name"])}


def overview(db: Session, ev: Evaluation) -> Dict[str, Any]:
    participants = db.execute(select(Participant).where(Participant.evaluation_id == ev.id)
                              .order_by(Participant.created_at)).scalars().all()
    sets = {str(s.participant_id): s for s in db.execute(select(ParticipantQuestionSet).where(
        ParticipantQuestionSet.evaluation_id == ev.id)).scalars().all()}
    readiness = {r["participant_id"]: r for r in participant_readiness(db, ev)}
    warnings = live_rater_warnings(db, ev.id)
    members = [p.board_member_id for p in participants if p.board_member_id]
    committees = _committees_by_member(db, members)
    rows = []
    for p in participants:
        pid = str(p.id)
        s = sets.get(pid)
        m = set_metrics(db, s) if s else None
        role = governance_role_from_participant_role(p.role)
        member = db.get(BoardMember, p.board_member_id) if p.board_member_id else None
        ready = readiness.get(pid)
        blockers = []
        if s is None and ready and ready["status"] != READY:
            blockers += ready["blocking_reasons"]
        if m:
            blockers += [g["message"] for g in m["coverage_gaps"]]
            if m["counts"]["pending_new"]:
                n = m["counts"]["pending_new"]
                blockers.append(f"{n} AI-proposed question{'' if n == 1 else 's'} awaiting a decision.")
        mine = [w for w in warnings if pid in w["participant_ids"]]
        rows.append({
            "participant_id": pid, "label": p.full_name or p.email,
            "display_code": member.display_code if member else None,
            "role_label": ROLE_LABELS.get(role or "", "Role not confirmed"),
            "committees": sorted(c["name"] for c in committees.get(str(p.board_member_id), [])),
            "status": s.status if s else "not_assembled",
            "questions": m["counts"]["questions"] if m else None,
            "estimated_minutes": m["estimated_minutes"] if m else None,
            "long": bool(m and m["estimated_minutes"] > LONG_SET_MINUTES),
            "open_suggestions": (m["counts"]["open_wording"] + m["counts"]["pending_new"]) if m else 0,
            "pending_new": m["counts"]["pending_new"] if m else 0,
            "coverage_gaps": len(m["coverage_gaps"]) if m else 0,
            "rater_warnings": [w["message"] for w in mine],
            "blockers": blockers,
            "ready": bool(ready and ready["status"] == READY),
            "approved_by": s.approved_by if s else None,
            "override_reason": s.override_reason if s else None,
        })
    return {"evaluation_id": ev.id, "long_set_minutes": LONG_SET_MINUTES, "participants": rows,
            "rater_warnings": warnings}


# ----------------------------
# By subject
# ----------------------------

def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def subjects_overview(db: Session, ev: Evaluation) -> List[Dict[str, Any]]:
    """Every subject with questions in the evaluation's sets: how many questions and raters."""
    options = subject_options(db, ev)
    rows = db.execute(select(Question).where(Question.evaluation_id == ev.id,
                                             Question.participant_id.is_not(None))).scalars().all()
    active = active_questions(list(rows))
    out = []
    for s in options:
        about = [q for q in active if str(q.evaluation_subject_id) == s["id"]]
        raters = {str(q.participant_id) for q in about if str(q.participant_id) != (s["participant_id"] or "")}
        out.append({**s, "questions": len(about), "rater_count": len(raters),
                    "too_few_raters": 0 < len(raters) < MIN_RATERS or (not raters and bool(about))})
    return out


def by_subject(db: Session, ev: Evaluation, subject_id: str) -> Dict[str, Any]:
    """Every question about one subject across all participants, grouped by bank item."""
    row = _subject_for(db, ev, subject_id)
    qs = active_questions(list(db.execute(select(Question).where(
        Question.evaluation_id == ev.id, Question.evaluation_subject_id == row.id,
        Question.participant_id.is_not(None)).order_by(Question.sort_order)).scalars().all()))
    people = {str(p.id): p for p in db.execute(select(Participant).where(Participant.evaluation_id == ev.id)).scalars()}
    sets = {str(s.participant_id): s.status for s in db.execute(select(ParticipantQuestionSet).where(
        ParticipantQuestionSet.evaluation_id == ev.id)).scalars()}
    items = {i.id: i for i in db.execute(select(QuestionBankItem).where(
        QuestionBankItem.id.in_({q.bank_item_id for q in qs if q.bank_item_id}))).scalars().all()}
    groups: Dict[str, Dict[str, Any]] = {}
    for q in qs:
        item = items.get(q.bank_item_id)
        key = item.code if item else f"own:{q.id}"
        g = groups.setdefault(key, {
            "key": key, "code": item.code if item else None, "bank_text": q.bank_text if item else None,
            "source": "bank" if item else ("ai_new" if q.text_source == "ai_new" else "consultant_written"),
            "answer_type": q.answer_type, "section": q.section, "sort": q.sort_order or 0, "entries": []})
        p = people.get(str(q.participant_id))
        g["entries"].append({"participant_id": str(q.participant_id), "label": (p.full_name or p.email) if p else "",
                             "question_id": str(q.id), "text": q.text, "text_source": q.text_source,
                             "set_status": sets.get(str(q.participant_id))})
    out = []
    for g in groups.values():
        texts = sorted({e["text"].strip() for e in g["entries"]})
        lowest = min((_similarity(a, b) for i, a in enumerate(texts) for b in texts[i + 1:]), default=1.0)
        out.append({**g, "wordings": len(texts), "worded_differently": lowest < WORDING_SIMILARITY_FLAG})
    out.sort(key=lambda g: (SECTIONS.index(g["section"]) if g["section"] in SECTIONS else 99, g["sort"], g["key"]))
    raters = {str(q.participant_id) for q in qs if str(q.participant_id) != str(row.participant_id or "")}
    return {
        "subject": {"id": str(row.id), "type": row.subject_type_code, "label": row.label},
        "questions": len(qs),
        "rater_count": len(raters),
        "too_few_raters": len(raters) < MIN_RATERS,
        "min_raters": MIN_RATERS,
        "raters": sorted((people[r].full_name or people[r].email) for r in raters if r in people),
        "groups": out,
    }


def metrics_response(db: Session, pset: ParticipantQuestionSet) -> Dict[str, Any]:
    """What every edit returns: fresh counts, coverage, gaps, time and the evaluation's rater warnings."""
    m = refresh_summary(db, pset)
    return {**m, "status": pset.status, "rater_warnings": live_rater_warnings(db, pset.evaluation_id)}

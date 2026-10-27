"""
app.services.question_sets
--------------------------
A participant's assembled question set after assembly: consultant decisions
on wording and AI new-question suggestions (each recorded with who and when),
the set lifecycle (draft -> approved -> locked) and the bank feedback loop
(accepted AI wording per bank item; promote to a new DRAFT bank version).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AssemblyRun,
    Evaluation,
    EvaluationContextSnapshot,
    EvaluationSubject,
    ParticipantQuestionSet,
    Participant,
    Question,
    QuestionBankItem,
    QuestionSuggestionDecision,
)
from app.services import question_bank as bank
from app.services import question_tailoring as ai
from app.services.question_assembly import SECTIONS, SetConflict, TailoringContext
from app.services.question_selection import ROLE_LABELS, build_selection_context

SECTION_LABELS = {
    "board": "About the board", "committees": "Your committees", "colleagues": "Your colleagues",
    "yourself": "About yourself", "confirm": "Please confirm", "additional": "Additional questions",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def question_set(db: Session, participant_id) -> Optional[ParticipantQuestionSet]:
    return db.execute(select(ParticipantQuestionSet).where(
        ParticipantQuestionSet.participant_id == participant_id)).scalars().first()


def set_questions(db: Session, participant_id) -> List[Question]:
    return list(db.execute(select(Question).where(Question.participant_id == participant_id)
                           .order_by(Question.sort_order, Question.id)).scalars().all())


def _require_draft(db: Session, q: Question) -> ParticipantQuestionSet:
    pset = question_set(db, q.participant_id)
    if pset is None or pset.status != "draft":
        raise SetConflict(f"The set is {pset.status if pset else 'missing'}; only draft sets can be changed.")
    return pset


def _record(db: Session, q: Question, decision: str, by: str, note: Optional[str] = None) -> QuestionSuggestionDecision:
    item = db.get(QuestionBankItem, q.bank_item_id) if q.bank_item_id else None
    d = QuestionSuggestionDecision(
        question_id=q.id, evaluation_id=q.evaluation_id, participant_id=q.participant_id, bank_item_id=q.bank_item_id,
        bank_item_code=item.code if item else None, bank_item_version=q.bank_item_version, decision=decision,
        bank_text=q.bank_text, ai_text=q.ai_text, final_text=q.text, note=note, decided_by=by or "consultant",
    )
    db.add(d)
    db.flush()
    return d


# ----------------------------
# Wording and new-question decisions
# ----------------------------

def choose_wording(db: Session, q: Question, use: str, by: str, text: Optional[str] = None,
                   note: Optional[str] = None) -> Question:
    """use: "bank" | "ai" | "edited". Tags never change: only the wording does."""
    _require_draft(db, q)
    if q.text_source == "ai_new":
        if use != "edited" or not (text or "").strip():
            raise ValueError("A new question can only be edited (give the text), accepted or rejected.")
        q.text = text.strip()
        _record(db, q, "edit", by, note)
        return q
    if use == "bank":
        q.text, q.text_source = q.bank_text, "bank"
        _record(db, q, "use_bank", by, note)
    elif use == "ai":
        if not q.ai_text:
            raise ValueError("There's no AI suggestion for this question.")
        q.text, q.text_source = q.ai_text, "ai_tailored"
        _record(db, q, "use_ai", by, note)
    elif use == "edited":
        if not (text or "").strip():
            raise ValueError("Give the edited text.")
        q.text, q.text_source = text.strip(), "consultant_edited"
        _record(db, q, "edit", by, note)
    else:
        raise ValueError("use must be bank, ai or edited.")
    db.flush()
    return q


def decide_new(db: Session, q: Question, accept: bool, by: str, note: Optional[str] = None) -> Question:
    _require_draft(db, q)
    if q.text_source != "ai_new":
        raise ValueError("Only AI new-question suggestions can be accepted or rejected.")
    q.suggestion_status = "accepted" if accept else "rejected"
    _record(db, q, "accept_new" if accept else "reject_new", by, note)
    return q


def regenerate(db: Session, q: Question, note: str = "", llm_call: Optional[ai.LLMCall] = None) -> Dict[str, Any]:
    """Ask again for one question's suggestion, optionally with a consultant note."""
    if not ai.ai_tailoring_enabled():
        raise SetConflict("AI tailoring is off (AI_TAILORING_ENABLED).")
    pset = _require_draft(db, q)
    if q.text_source in ("ai_new", "consultant_edited"):
        raise ValueError("Only bank or AI-tailored questions have wording suggestions.")
    ev = db.get(Evaluation, q.evaluation_id)
    run = db.get(AssemblyRun, pset.assembly_run_id) if pset.assembly_run_id else None
    snap = db.get(EvaluationContextSnapshot, run.snapshot_id) if run and run.snapshot_id else None
    if snap is None:
        raise SetConflict("Assemble the set first (no context snapshot).")
    base = build_selection_context(db, ev)
    ctx = TailoringContext(db, ev, base, snap, llm_call)
    person = next(p for p in base["people"] if p["participant_id"] == str(q.participant_id))
    subject = db.get(EvaluationSubject, q.evaluation_subject_id) if q.evaluation_subject_id else None
    subject_name = None
    if subject is not None and subject.participant_id:
        subject_name = next((p["label"].split(" · ", 1)[-1] for p in base["people"]
                             if p["participant_id"] == str(subject.participant_id)), None)
    labels = (q.scale or {}).get("labels") or {}
    sent = [{"question_id": str(q.id), "bank_text": q.bank_text, "answer_type": q.answer_type, "options": q.options,
             "scale_labels": [labels[k] for k in sorted(labels, key=int)] or None,
             "subject": {"label": subject_name or (subject.label if subject else ""),
                         "type": subject.subject_type_code if subject else None},
             "subject_name": subject_name,
             "committee": subject.committee_name if subject is not None and subject.committee_name else None,
             "clauses": ctx._clauses(q.bank_item_id)}]
    context = {**ctx.context, "respondent": {"role": ROLE_LABELS.get(person.get("role") or "", "Director"),
                                             "tone_notes": ctx._tone(person["participant_id"])}}
    checked = ai.tailor(sent, context, ai.vocabulary(context, sent), ctx.people, llm_call, note=note)
    if checked.accepted:
        q.ai_text, q.ai_reason = checked.accepted[0]["text"], checked.accepted[0]["reason"]
    db.flush()
    return {"accepted": bool(checked.accepted), "dropped": checked.dropped}


# ----------------------------
# Lifecycle
# ----------------------------

def approve_set(db: Session, pset: ParticipantQuestionSet, by: str, override_reason: Optional[str] = None) -> ParticipantQuestionSet:
    if pset.status != "draft":
        raise SetConflict(f"The set is already {pset.status}.")
    gaps = (pset.summary or {}).get("coverage_gaps") or []
    if gaps and not (override_reason or "").strip():
        raise SetConflict(f"{len(gaps)} coverage gap(s) remain: "
                          + "; ".join(g["message"] for g in gaps) + " Give an override reason to approve anyway.")
    for q in set_questions(db, pset.participant_id):
        if q.text_source == "ai_new" and q.suggestion_status != "accepted":
            continue  # pending or rejected suggestions never reach a participant
        q.status = "approved"
    pset.status = "approved"
    pset.override_reason = override_reason.strip() if gaps and override_reason else None
    pset.approved_by = by or "consultant"
    pset.approved_at = _now()
    db.flush()
    return pset


def lock_set(db: Session, pset: ParticipantQuestionSet) -> ParticipantQuestionSet:
    """Called when the participant first opens the form; an approved set can't change after this."""
    if pset.status == "locked":
        return pset
    if pset.status != "approved":
        raise SetConflict("Only an approved set can be locked.")
    for q in set_questions(db, pset.participant_id):
        if q.status == "approved":
            q.status = "locked"
    pset.status = "locked"
    pset.locked_at = _now()
    db.flush()
    return pset


# ----------------------------
# API shape
# ----------------------------

def question_dict(q: Question, codes: Dict[str, str], subjects: Dict[str, EvaluationSubject]) -> Dict[str, Any]:
    subject = subjects.get(str(q.evaluation_subject_id)) if q.evaluation_subject_id else None
    return {
        "id": str(q.id), "section": q.section, "sort_order": q.sort_order, "status": q.status,
        "bank_item_id": str(q.bank_item_id) if q.bank_item_id else None,
        "bank_item_code": codes.get(str(q.bank_item_id)) if q.bank_item_id else None,
        "bank_item_version": q.bank_item_version,
        "subject": ({"id": str(subject.id), "type": subject.subject_type_code, "label": subject.label}
                    if subject else None),
        "text": q.text, "bank_text": q.bank_text, "ai_text": q.ai_text, "ai_reason": q.ai_reason,
        "text_source": q.text_source, "suggestion_status": q.suggestion_status, "ai_fact_key": q.ai_fact_key,
        "answer_type": q.answer_type, "options": q.options, "scale": q.scale,
        "theme_code": q.theme_code, "evidence_source_code": q.evidence_source_code,
        "subject_types": q.subject_type_codes, "dimension": q.dimension,
        "depends_on_question_id": str(q.depends_on_question_id) if q.depends_on_question_id else None,
        "show_if": q.show_if, "confirm_value": q.confirm_value,
    }


def set_dict(db: Session, ev_id: str, participant: Participant) -> Dict[str, Any]:
    pset = question_set(db, participant.id)
    questions = set_questions(db, participant.id)
    codes = {str(i.id): i.code for i in db.execute(select(QuestionBankItem).where(
        QuestionBankItem.id.in_([q.bank_item_id for q in questions if q.bank_item_id]))).scalars().all()}
    subjects = {str(s.id): s for s in db.execute(select(EvaluationSubject).where(
        EvaluationSubject.evaluation_id == ev_id)).scalars().all()}
    run = db.execute(select(AssemblyRun).where(AssemblyRun.evaluation_id == ev_id, AssemblyRun.status == "done")
                     .order_by(AssemblyRun.created_at.desc()).limit(1)).scalars().first()
    rendered = [question_dict(q, codes, subjects) for q in questions]
    return {
        "participant_id": str(participant.id),
        "label": participant.full_name or participant.email,
        "set": None if pset is None else {
            "id": str(pset.id), "status": pset.status, "estimated_minutes": pset.estimated_minutes,
            "summary": pset.summary, "override_reason": pset.override_reason, "approved_by": pset.approved_by,
            "approved_at": _iso(pset.approved_at), "locked_at": _iso(pset.locked_at),
            "assembly_run_id": str(pset.assembly_run_id) if pset.assembly_run_id else None,
        },
        "sections": [{"key": s, "label": SECTION_LABELS[s], "questions": [q for q in rendered if q["section"] == s]}
                     for s in SECTIONS if any(q["section"] == s for q in rendered)],
        "rater_warnings": run.rater_warnings if run else [],
    }


def run_dict(run: AssemblyRun) -> Dict[str, Any]:
    return {
        "id": str(run.id), "evaluation_id": run.evaluation_id, "status": run.status,
        "participant_ids": run.participant_ids, "reset": run.reset, "include_drafts": run.include_drafts,
        "ai_enabled": run.ai_enabled, "snapshot_id": str(run.snapshot_id) if run.snapshot_id else None,
        "results": run.results, "rater_warnings": run.rater_warnings, "error": run.error,
        "requested_by": run.requested_by, "created_at": _iso(run.created_at), "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


# ----------------------------
# Bank feedback loop
# ----------------------------

def suggestions_report(db: Session) -> List[Dict[str, Any]]:
    """Per bank item: AI wording offered, accepted (and in how many evaluations), edited, with examples."""
    offered = dict(db.execute(
        select(QuestionBankItem.code, func.count(Question.id))
        .join(QuestionBankItem, QuestionBankItem.id == Question.bank_item_id)
        .where(Question.ai_text.is_not(None), Question.text_source != "ai_new")
        .group_by(QuestionBankItem.code)).all())
    out: Dict[str, Dict[str, Any]] = {}
    rows = db.execute(select(QuestionSuggestionDecision).where(
        QuestionSuggestionDecision.bank_item_code.is_not(None),
        QuestionSuggestionDecision.decision.in_(("use_ai", "edit")))
        .order_by(QuestionSuggestionDecision.decided_at.desc())).scalars().all()
    for d in rows:
        e = out.setdefault(d.bank_item_code, {"code": d.bank_item_code, "accepted": 0, "edited": 0,
                                              "evaluations": set(), "examples": []})
        e["accepted" if d.decision == "use_ai" else "edited"] += 1
        e["evaluations"].add(d.evaluation_id)
        if d.decision == "use_ai" and len(e["examples"]) < 5:
            e["examples"].append({"question_id": str(d.question_id) if d.question_id else None,
                                  "evaluation_id": d.evaluation_id, "bank_text": d.bank_text, "text": d.final_text,
                                  "bank_item_version": d.bank_item_version, "decided_by": d.decided_by,
                                  "decided_at": _iso(d.decided_at)})
    for code, n in offered.items():
        out.setdefault(code, {"code": code, "accepted": 0, "edited": 0, "evaluations": set(), "examples": []})
    latest = {i.code: i for i in bank.list_items(db) if i.code in out}
    report = []
    for code, e in out.items():
        item = latest.get(code)
        report.append({**e, "evaluations": len(e["evaluations"]), "offered": offered.get(code, 0),
                       "bank_item_id": str(item.id) if item else None,
                       "latest_version": item.version if item else None, "latest_status": item.status if item else None})
    return sorted(report, key=lambda r: (-r["accepted"], r["code"]))


def promote_to_bank(db: Session, item: QuestionBankItem, q: Question, by: str) -> QuestionBankItem:
    """New DRAFT version of the bank item with the question's accepted wording. Approved versions never change."""
    if str(q.bank_item_id) != str(item.id):
        raise ValueError("That question wasn't assembled from this bank item.")
    if q.text_source not in ("ai_tailored", "consultant_edited"):
        raise ValueError("Only accepted AI wording or a consultant's edit can be promoted.")
    if item.status != "approved":
        raise SetConflict(f"{item.code} v{item.version} is {item.status}; only approved items are promoted.")
    latest = bank.latest_version(db, item.code)
    if latest.id != item.id:
        raise SetConflict(f"{item.code} already has version {latest.version}; review that one instead.")
    if item.placeholders:
        raise SetConflict(f"{item.code} is templated ({', '.join(item.placeholders)}); edit its wording in the bank by hand "
                          "so the placeholders are kept.")
    note = (f"Promoted by {by or 'consultant'} from wording accepted in evaluation {q.evaluation_id}. "
            "Check it isn't specific to one company before approving.")
    new, _ = bank.update_item(db, item, {"text": q.text, "review_notes": note})
    return new

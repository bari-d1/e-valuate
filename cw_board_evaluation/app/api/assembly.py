"""
app.api.assembly
----------------
Question assembly: one tailored draft set per participant, consultant
decisions, the set lifecycle and the bank feedback loop.

Endpoints (all under /api/v1, consultant auth):
- GET/PUT /evaluations/{id}/options                          (peer_mode, ...)
- POST /evaluations/{id}/assembly                            (all ready participants, or participant_ids)
- GET  /evaluations/{id}/assembly-runs, /evaluations/{id}/assembly-runs/{run_id}
- GET  /evaluations/{id}/participants/{pid}/question-set
- PATCH /evaluations/{id}/assembled-questions/{qid}          (use bank / ai / edited text)
- POST /evaluations/{id}/assembled-questions/{qid}/regenerate
- POST /evaluations/{id}/assembled-questions/{qid}/accept | /reject   (AI new questions)
- POST /evaluations/{id}/participants/{pid}/question-set/approve | /lock
- GET  /question-bank/suggestions-report
- POST /question-bank/items/{item_id}/promote

The consultant is identified by the optional X-Consultant-Name header (the
shared API key carries no identity); decisions record it with the time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.organisations import _uuid
from app.db.models import AssemblyRun, Evaluation, EvaluationSubject, Participant, Question, QuestionBankItem
from app.db.session import get_db
from app.domain.evaluation_options import EVALUATION_OPTIONS, OptionError, effective_options, validate_options
from app.services import question_assembly as assembly
from app.services import question_sets as sets
from app.services.question_bank import item_dict

router = APIRouter()


def consultant_name(x_consultant_name: Optional[str] = Header(default=None, alias="X-Consultant-Name")) -> str:
    return (x_consultant_name or "").strip()[:255] or "consultant"


def _evaluation_or_404(db: Session, evaluation_id: str) -> Evaluation:
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    return ev


def _participant_or_404(db: Session, ev: Evaluation, participant_id: str) -> Participant:
    p = db.get(Participant, _uuid(participant_id, "Participant"))
    if not p or p.evaluation_id != ev.id:
        raise HTTPException(status_code=404, detail="Participant not found in this evaluation.")
    return p


def _question_or_404(db: Session, ev: Evaluation, question_id: str) -> Question:
    q = db.get(Question, _uuid(question_id, "Question"))
    if not q or q.evaluation_id != ev.id or q.participant_id is None:
        raise HTTPException(status_code=404, detail="Assembled question not found in this evaluation.")
    return q


def _set_or_404(db: Session, p: Participant):
    pset = sets.question_set(db, p.id)
    if pset is None:
        raise HTTPException(status_code=404, detail="No assembled set for this participant yet.")
    return pset


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except assembly.SetConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (assembly.AssemblyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ----------------------------
# Evaluation options
# ----------------------------

class OptionsIn(BaseModel):
    options: Dict[str, Any]


@router.get("/evaluations/{evaluation_id}/options")
def get_options(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    return {"options": effective_options(ev.options), "available": EVALUATION_OPTIONS}


@router.put("/evaluations/{evaluation_id}/options")
def set_options(evaluation_id: str, payload: OptionsIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    try:
        ev.options = {**(ev.options or {}), **validate_options(payload.options)}
    except OptionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return {"options": effective_options(ev.options), "available": EVALUATION_OPTIONS}


# ----------------------------
# Runs
# ----------------------------

class AssemblyIn(BaseModel):
    participant_ids: Optional[List[str]] = None
    reset: bool = False
    include_drafts: bool = False


@router.post("/evaluations/{evaluation_id}/assembly", status_code=202)
def start_assembly(evaluation_id: str, background: BackgroundTasks, payload: Optional[AssemblyIn] = None,
                   db: Session = Depends(get_db), by: str = Depends(consultant_name)) -> Dict[str, Any]:
    """Queue an assembly run; it runs in the background. Poll the run for its status."""
    ev = _evaluation_or_404(db, evaluation_id)
    payload = payload or AssemblyIn()
    run = _call(assembly.create_run, db, ev, participant_ids=payload.participant_ids, reset=payload.reset,
                include_drafts=payload.include_drafts, requested_by=by)
    db.commit()
    background.add_task(assembly.execute_run, run.id)
    return sets.run_dict(run)


@router.get("/evaluations/{evaluation_id}/assembly-runs")
def list_runs(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    _evaluation_or_404(db, evaluation_id)
    runs = db.execute(select(AssemblyRun).where(AssemblyRun.evaluation_id == evaluation_id)
                      .order_by(AssemblyRun.created_at.desc()).limit(20)).scalars().all()
    return {"items": [sets.run_dict(r) for r in runs]}


@router.get("/evaluations/{evaluation_id}/assembly-runs/{run_id}")
def get_run(evaluation_id: str, run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    run = db.get(AssemblyRun, _uuid(run_id, "Assembly run"))
    if not run or run.evaluation_id != evaluation_id:
        raise HTTPException(status_code=404, detail="Assembly run not found.")
    return sets.run_dict(run)


# ----------------------------
# A participant's set
# ----------------------------

@router.get("/evaluations/{evaluation_id}/participants/{participant_id}/question-set")
def get_set(evaluation_id: str, participant_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    return sets.set_dict(db, ev.id, _participant_or_404(db, ev, participant_id))


class WordingIn(BaseModel):
    use: str  # "bank" | "ai" | "edited"
    text: Optional[str] = None
    note: Optional[str] = None


class NoteIn(BaseModel):
    note: Optional[str] = None


def _question_response(db: Session, q: Question) -> Dict[str, Any]:
    codes = {str(q.bank_item_id): db.get(QuestionBankItem, q.bank_item_id).code} if q.bank_item_id else {}
    subjects = {str(q.evaluation_subject_id): db.get(EvaluationSubject, q.evaluation_subject_id)} \
        if q.evaluation_subject_id else {}
    return sets.question_dict(q, codes, subjects)


@router.patch("/evaluations/{evaluation_id}/assembled-questions/{question_id}")
def choose_wording(evaluation_id: str, question_id: str, payload: WordingIn, db: Session = Depends(get_db),
                   by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    q = _call(sets.choose_wording, db, _question_or_404(db, ev, question_id), payload.use, by, payload.text, payload.note)
    db.commit()
    return _question_response(db, q)


@router.post("/evaluations/{evaluation_id}/assembled-questions/{question_id}/regenerate")
def regenerate(evaluation_id: str, question_id: str, payload: Optional[NoteIn] = None,
               db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    q = _question_or_404(db, ev, question_id)
    outcome = _call(sets.regenerate, db, q, (payload.note if payload else None) or "")
    db.commit()
    return {**outcome, "question": _question_response(db, q)}


@router.post("/evaluations/{evaluation_id}/assembled-questions/{question_id}/accept")
def accept_new(evaluation_id: str, question_id: str, payload: Optional[NoteIn] = None, db: Session = Depends(get_db),
               by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    q = _call(sets.decide_new, db, _question_or_404(db, ev, question_id), True, by, payload.note if payload else None)
    db.commit()
    return _question_response(db, q)


@router.post("/evaluations/{evaluation_id}/assembled-questions/{question_id}/reject")
def reject_new(evaluation_id: str, question_id: str, payload: Optional[NoteIn] = None, db: Session = Depends(get_db),
               by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    q = _call(sets.decide_new, db, _question_or_404(db, ev, question_id), False, by, payload.note if payload else None)
    db.commit()
    return _question_response(db, q)


class ApproveIn(BaseModel):
    override_reason: Optional[str] = None


@router.post("/evaluations/{evaluation_id}/participants/{participant_id}/question-set/approve")
def approve_set(evaluation_id: str, participant_id: str, payload: Optional[ApproveIn] = None,
                db: Session = Depends(get_db), by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    p = _participant_or_404(db, ev, participant_id)
    _call(sets.approve_set, db, _set_or_404(db, p), by, payload.override_reason if payload else None)
    db.commit()
    return sets.set_dict(db, ev.id, p)


@router.post("/evaluations/{evaluation_id}/participants/{participant_id}/question-set/lock")
def lock_set(evaluation_id: str, participant_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation_or_404(db, evaluation_id)
    p = _participant_or_404(db, ev, participant_id)
    _call(sets.lock_set, db, _set_or_404(db, p))
    db.commit()
    return sets.set_dict(db, ev.id, p)


# ----------------------------
# Bank feedback loop
# ----------------------------

@router.get("/question-bank/suggestions-report")
def suggestions_report(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return {"items": sets.suggestions_report(db)}


class PromoteIn(BaseModel):
    question_id: str


@router.post("/question-bank/items/{item_id}/promote", status_code=201)
def promote(item_id: str, payload: PromoteIn, db: Session = Depends(get_db),
            by: str = Depends(consultant_name)) -> Dict[str, Any]:
    item = db.get(QuestionBankItem, _uuid(item_id, "Question bank item"))
    if not item:
        raise HTTPException(status_code=404, detail="Question bank item not found.")
    q = db.get(Question, _uuid(payload.question_id, "Question"))
    if not q or q.participant_id is None:
        raise HTTPException(status_code=404, detail="Assembled question not found.")
    new = _call(sets.promote_to_bank, db, item, q, by)
    db.commit()
    return {"item": item_dict(new)}

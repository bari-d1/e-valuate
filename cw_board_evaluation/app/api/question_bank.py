"""
app.api.question_bank
---------------------
The question bank (the firm's methodology as data) and the per-participant
question preview.

Endpoints (all under /api/v1, consultant auth):
- GET  /question-bank/meta
- GET  /question-bank/items?subject_type=&theme=&evidence_source=&status=&q=&all_versions=
- POST /question-bank/items
- GET  /question-bank/items/{item_id}                (with every version of its code)
- PATCH /question-bank/items/{item_id}              (approved items get a new draft version)
- POST /question-bank/items/{item_id}/approve | /retire
- POST /question-bank/rules/validate
- POST /question-bank/items/{item_id}/clauses       (link a clause by code + reference)
- POST /question-bank/items/{item_id}/clauses/{clause_id}/confirm
- DELETE /question-bank/items/{item_id}/clauses/{clause_id}
- GET  /evaluations/{evaluation_id}/question-preview?participant_id=&include_drafts=

Validation errors come back as 400 with detail {"message", "errors": [...]}.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.organisations import _uuid
from app.db.models import Evaluation, EvidenceSource, GovernanceCode, QuestionBankItem, SubjectType, Theme
from app.db.session import get_db
from app.domain.board_member_profile import GOVERNANCE_ROLES
from app.domain.governance import SECTOR_KEYS
from app.domain.org_profile import COMMITTEE_TYPES
from app.domain.question_bank import (
    ANSWER_TYPES,
    KNOWN_FROM_BEHAVIOURS,
    SCALES,
    SECONDS_PER_ANSWER,
    STATUSES,
    SUBJECT_BINDINGS,
    BankItemError,
)
from app.domain.question_rules import all_fact_keys, conditions_for_ui, describe_rule, validate_rule
from app.services import question_bank as svc
from app.services.question_selection import preview

router = APIRouter()


# ----------------------------
# Helpers
# ----------------------------

def _item_or_404(db: Session, item_id: str) -> QuestionBankItem:
    item = db.get(QuestionBankItem, _uuid(item_id, "Question bank item"))
    if not item:
        raise HTTPException(status_code=404, detail="Question bank item not found.")
    return item


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BankItemError as e:
        raise HTTPException(status_code=400, detail={"message": "The item isn't valid.", "errors": e.errors})
    except svc.BankConflict as e:
        raise HTTPException(status_code=409, detail=str(e))


def _with_versions(db: Session, item: QuestionBankItem) -> Dict[str, Any]:
    versions = svc.versions_of(db, item.code)
    return {
        "item": svc.item_dict(item),
        "latest_version": versions[-1].version,
        "versions": [{"id": str(v.id), "version": v.version, "status": v.status,
                      "approved_at": v.approved_at.isoformat() if v.approved_at else None,
                      "created_at": v.created_at.isoformat() if v.created_at else None} for v in versions],
    }


# ----------------------------
# Vocabulary
# ----------------------------

@router.get("/question-bank/meta")
def get_meta(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Everything the bank editor needs to render choices and explain the rule language."""
    return {
        "statuses": list(STATUSES),
        "answer_types": list(ANSWER_TYPES),
        "subject_bindings": list(SUBJECT_BINDINGS),
        "known_from_behaviours": list(KNOWN_FROM_BEHAVIOURS),
        "scales": SCALES,
        "seconds_per_answer": SECONDS_PER_ANSWER,
        "fact_keys": all_fact_keys(),
        "conditions": conditions_for_ui(),
        "governance_roles": GOVERNANCE_ROLES,
        "committee_types": list(COMMITTEE_TYPES),
        "sectors": SECTOR_KEYS,
        "governance_codes": [c for c in db.execute(select(GovernanceCode.code).order_by(GovernanceCode.code)).scalars().all()],
        "subject_types": [{"code": t.code, "name": t.name} for t in db.execute(
            select(SubjectType).where(SubjectType.active == 1).order_by(SubjectType.sort_order)).scalars().all()],
        "themes": [{"code": t.code, "name": t.name} for t in db.execute(
            select(Theme).where(Theme.active == 1).order_by(Theme.sort_order)).scalars().all()],
        "evidence_sources": [{"code": e.code, "name": e.name} for e in db.execute(
            select(EvidenceSource).order_by(EvidenceSource.sort_order)).scalars().all()],
    }


# ----------------------------
# Items
# ----------------------------

class ItemIn(BaseModel):
    code: str
    text: str
    answer_type: str
    options: Optional[List[str]] = None
    scale: Optional[Dict[str, Any]] = None
    subject_types: List[str]
    subject_binding: str
    respondent_rule: Optional[Dict[str, Any]] = None
    activation_rule: Optional[Dict[str, Any]] = None
    theme_code: str
    evidence_source_code: str
    known_from: Optional[str] = None
    known_from_behaviour: str = "skip"
    placeholders: List[str] = []
    guidance: Optional[str] = None
    source_refs: List[Dict[str, Any]] = []
    tag_notes: Dict[str, Any] = {}
    weight: float = 1
    sort_order: int = 0
    review_notes: Optional[str] = None


class ItemPatch(BaseModel):
    text: Optional[str] = None
    answer_type: Optional[str] = None
    options: Optional[List[str]] = None
    scale: Optional[Dict[str, Any]] = None
    subject_types: Optional[List[str]] = None
    subject_binding: Optional[str] = None
    respondent_rule: Optional[Dict[str, Any]] = None
    activation_rule: Optional[Dict[str, Any]] = None
    theme_code: Optional[str] = None
    evidence_source_code: Optional[str] = None
    known_from: Optional[str] = None
    known_from_behaviour: Optional[str] = None
    placeholders: Optional[List[str]] = None
    guidance: Optional[str] = None
    tag_notes: Optional[Dict[str, Any]] = None
    weight: Optional[float] = None
    sort_order: Optional[int] = None
    review_notes: Optional[str] = None


@router.get("/question-bank/items")
def list_items(subject_type: Optional[str] = None, theme: Optional[str] = None, evidence_source: Optional[str] = None,
               status: Optional[str] = None, q: Optional[str] = None, all_versions: bool = False,
               db: Session = Depends(get_db)) -> Dict[str, Any]:
    items = svc.list_items(db, subject_type=subject_type or None, theme=theme or None,
                           evidence_source=evidence_source or None, status=status or None, q=q, all_versions=all_versions)
    counts: Dict[str, int] = {s: 0 for s in STATUSES}
    for i in svc.list_items(db):
        counts[i.status] += 1
    return {"items": [svc.item_dict(i) for i in items], "total": len(items), "status_counts": counts}


@router.post("/question-bank/items", status_code=201)
def create_item(payload: ItemIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = _call(svc.create_item, db, payload.model_dump())
    db.commit()
    return _with_versions(db, item)


@router.get("/question-bank/items/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _with_versions(db, _item_or_404(db, item_id))


@router.patch("/question-bank/items/{item_id}")
def update_item(item_id: str, payload: ItemPatch, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = _item_or_404(db, item_id)
    item, new_version = _call(svc.update_item, db, item, payload.model_dump(exclude_unset=True))
    db.commit()
    return {**_with_versions(db, item), "new_version": new_version}


@router.post("/question-bank/items/{item_id}/approve")
def approve_item(item_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = _call(svc.approve_item, db, _item_or_404(db, item_id))
    db.commit()
    return _with_versions(db, item)


@router.post("/question-bank/items/{item_id}/retire")
def retire_item(item_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = _call(svc.retire_item, db, _item_or_404(db, item_id))
    db.commit()
    return _with_versions(db, item)


# ----------------------------
# Rules
# ----------------------------

class RuleIn(BaseModel):
    rule: Optional[Any] = None


@router.post("/question-bank/rules/validate")
def validate(payload: RuleIn) -> Dict[str, Any]:
    errors = validate_rule(payload.rule)
    return {"valid": not errors, "errors": errors, "description": None if errors else describe_rule(payload.rule)}


# ----------------------------
# Governance clause links
# ----------------------------

class ClauseIn(BaseModel):
    code: str
    reference: str


@router.post("/question-bank/items/{item_id}/clauses", status_code=201)
def add_clause(item_id: str, payload: ClauseIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = _item_or_404(db, item_id)
    clause = svc.find_clause(db, payload.code.strip(), payload.reference.strip())
    if clause is None:
        raise HTTPException(status_code=400, detail=f"No clause {payload.reference} in {payload.code}.")
    svc.link_clause(db, item, clause, "confirmed")
    db.commit()
    return _with_versions(db, item)


@router.post("/question-bank/items/{item_id}/clauses/{clause_id}/confirm")
def confirm_clause(item_id: str, clause_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = _item_or_404(db, item_id)
    link = svc.clause_link(item, clause_id)
    if link is None:
        raise HTTPException(status_code=404, detail="That clause isn't linked to this item.")
    link.status = "confirmed"
    db.commit()
    return _with_versions(db, item)


@router.delete("/question-bank/items/{item_id}/clauses/{clause_id}")
def remove_clause(item_id: str, clause_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = _item_or_404(db, item_id)
    link = svc.clause_link(item, clause_id)
    if link is None:
        raise HTTPException(status_code=404, detail="That clause isn't linked to this item.")
    svc.remove_clause_link(db, item, link)
    db.commit()
    return _with_versions(db, item)


# ----------------------------
# Preview
# ----------------------------

@router.get("/evaluations/{evaluation_id}/question-preview")
def question_preview(evaluation_id: str, participant_id: Optional[str] = None, include_drafts: bool = False,
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Which items each participant would get, about which subject, and why. Creates nothing."""
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    result = preview(db, ev, participant_id=participant_id, include_drafts=include_drafts)
    if participant_id and not result["participants"]:
        raise HTTPException(status_code=404, detail="Participant not found in this evaluation.")
    return result

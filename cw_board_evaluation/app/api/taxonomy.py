"""
app.api.taxonomy
----------------
Tagging vocabulary and evaluation subjects.

Endpoints:
- GET  /api/v1/taxonomy
- GET  /api/v1/evaluations/{evaluation_id}/subjects
- POST /api/v1/evaluations/{evaluation_id}/subjects/sync
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evaluation, EvidenceSource, SubjectType, Theme
from app.db.session import get_db
from app.services.evaluation_subjects import (
    EvaluationNotFound,
    list_evaluation_subjects,
    subject_to_dict,
    sync_evaluation_subjects,
)

router = APIRouter()


def _ensure_evaluation_exists(db: Session, evaluation_id: str) -> Evaluation:
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {evaluation_id}")
    return ev


@router.get("/taxonomy")
def get_taxonomy(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Active subject types, themes and evidence sources, in display order."""
    subject_types = db.execute(
        select(SubjectType).where(SubjectType.active == 1).order_by(SubjectType.sort_order, SubjectType.code)
    ).scalars().all()
    themes = db.execute(
        select(Theme).where(Theme.active == 1).order_by(Theme.sort_order, Theme.code)
    ).scalars().all()
    evidence_sources = db.execute(
        select(EvidenceSource).order_by(EvidenceSource.sort_order, EvidenceSource.code)
    ).scalars().all()

    return {
        "subject_types": [
            {
                "code": t.code,
                "name": t.name,
                "description": t.description,
                "cardinality": t.cardinality,
                "sort_order": t.sort_order,
            }
            for t in subject_types
        ],
        "themes": [
            {"code": t.code, "name": t.name, "description": t.description, "sort_order": t.sort_order}
            for t in themes
        ],
        "evidence_sources": [
            {"code": e.code, "name": e.name, "description": e.description, "sort_order": e.sort_order}
            for e in evidence_sources
        ],
    }


@router.get("/evaluations/{evaluation_id}/subjects")
def list_subjects(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    _ensure_evaluation_exists(db, evaluation_id)
    items = [subject_to_dict(s) for s in list_evaluation_subjects(db, evaluation_id)]
    return {"evaluation_id": evaluation_id, "count": len(items), "items": items}


@router.post("/evaluations/{evaluation_id}/subjects/sync")
def sync_subjects(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Create any missing subjects from the evaluation's data. Safe to repeat."""
    try:
        result = sync_evaluation_subjects(db, evaluation_id)
    except EvaluationNotFound:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {evaluation_id}")
    db.commit()
    result["counts"] = {
        "created": len(result["created"]),
        "existing": len(result["existing"]),
        "skipped": len(result["skipped"]),
    }
    return result

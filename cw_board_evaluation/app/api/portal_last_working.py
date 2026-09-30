"""
app.api.portal
--------------
Participant portal endpoints (token-based access).

Routes:
- GET  /api/v1/portal/{token}
- GET  /api/v1/portal/{token}/responses
- POST /api/v1/portal/{token}/responses

Purpose:
- Allow invited participants to open a portal link and submit answers securely via access_token.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Evaluation, Participant, Question, Response

router = APIRouter()


# -------------------------
# Helpers
# -------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_participant_by_token(db: Session, token: str) -> Participant:
    t = (token or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="Token is required.")

    p = (
        db.execute(select(Participant).where(Participant.access_token == t))
        .scalars()
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Invalid or expired participant link.")
    return p


def _ensure_evaluation(db: Session, evaluation_id: str) -> Evaluation:
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {evaluation_id}")
    return ev


def _get_active_questions(db: Session, template_code: str, version: int) -> List[Question]:
    return (
        db.execute(
            select(Question)
            .where(Question.template_code == template_code)
            .where(Question.version == int(version))
            .where(Question.active == 1)
            .order_by(Question.dimension.asc(), Question.created_at.asc())
        )
        .scalars()
        .all()
    )


def _validate_answer(q: Question, score: Optional[int], comment: Optional[str]) -> None:
    at = (q.answer_type or "").lower()

    if at == "rating":
        if score is None:
            raise HTTPException(status_code=400, detail=f"Missing score for rating question: {q.id}")
        if not (1 <= int(score) <= 5):
            raise HTTPException(status_code=400, detail=f"Score must be 1..5 for rating question: {q.id}")
        return

    if at == "yesno":
        if score is None:
            raise HTTPException(status_code=400, detail=f"Missing score for yes/no question: {q.id}")
        if int(score) not in (0, 1):
            raise HTTPException(status_code=400, detail=f"Score must be 0/1 for yes/no question: {q.id}")
        return

    if at == "comment":
        txt = (comment or "").strip()
        if not txt:
            raise HTTPException(status_code=400, detail=f"Missing comment for comment question: {q.id}")
        return

    # default fallback
    raise HTTPException(status_code=400, detail=f"Unsupported answer_type '{q.answer_type}' for question: {q.id}")


# -------------------------
# Schemas
# -------------------------

class PortalQuestionOut(BaseModel):
    question_id: str
    dimension: str
    text: str
    answer_type: str
    weight: int
    active: int


class PortalParticipantOut(BaseModel):
    participant_id: str
    email: str
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: str
    invited_at: Optional[str] = None
    responded_at: Optional[str] = None


class PortalEvaluationOut(BaseModel):
    evaluation_id: str
    tenant_name: str
    sector: str
    year: int
    regulators: List[str] = Field(default_factory=list)
    instrument: Dict[str, Any]


class PortalLoadOut(BaseModel):
    participant: PortalParticipantOut
    evaluation: PortalEvaluationOut
    questions: List[PortalQuestionOut]


class PortalAnswerIn(BaseModel):
    question_id: str
    score: Optional[int] = None
    comment: Optional[str] = None


class PortalSubmitIn(BaseModel):
    answers: List[PortalAnswerIn] = Field(default_factory=list)


class PortalResponseOut(BaseModel):
    question_id: str
    score: Optional[int] = None
    comment: Optional[str] = None
    created_at: Optional[str] = None


# -------------------------
# Routes
# -------------------------

@router.get("/portal/{token}", status_code=status.HTTP_200_OK, response_model=PortalLoadOut)
def portal_load(token: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    p = _ensure_participant_by_token(db, token)
    ev = _ensure_evaluation(db, p.evaluation_id)

    template_code = (ev.instrument_template_code or "DEFAULT").strip()
    version = int(ev.instrument_version or 1)

    questions = _get_active_questions(db, template_code=template_code, version=version)
    if not questions:
        raise HTTPException(status_code=400, detail="No active questions found for this evaluation's questionnaire.")

    return {
        "participant": {
            "participant_id": str(p.id),
            "email": p.email,
            "full_name": p.full_name,
            "role": p.role,
            "status": p.status,
            "invited_at": p.invited_at.isoformat() if p.invited_at else None,
            "responded_at": p.responded_at.isoformat() if p.responded_at else None,
        },
        "evaluation": {
            "evaluation_id": ev.id,
            "tenant_name": ev.tenant_name,
            "sector": ev.sector,
            "year": ev.year,
            "regulators": (ev.regulators or {}).get("items", []) if isinstance(ev.regulators, dict) else [],
            "instrument": {"template_code": template_code, "version": version},
        },
        "questions": [
            {
                "question_id": str(q.id),
                "dimension": q.dimension,
                "text": q.text,
                "answer_type": q.answer_type,
                "weight": int(q.weight or 1),
                "active": int(q.active or 1),
            }
            for q in questions
        ],
    }


@router.get("/portal/{token}/responses", status_code=status.HTTP_200_OK)
def portal_get_responses(token: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    p = _ensure_participant_by_token(db, token)
    ev = _ensure_evaluation(db, p.evaluation_id)

    template_code = (ev.instrument_template_code or "DEFAULT").strip()
    version = int(ev.instrument_version or 1)
    questions = _get_active_questions(db, template_code=template_code, version=version)

    qids = {q.id for q in questions}
    rows = (
        db.execute(
            select(Response)
            .where(Response.participant_id == p.id)
            .where(Response.question_id.in_(list(qids)) if qids else True)
        )
        .scalars()
        .all()
    )

    items = []
    for r in rows:
        items.append(
            {
                "question_id": str(r.question_id),
                "score": r.score,
                "comment": r.comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    return {
        "participant_id": str(p.id),
        "evaluation_id": ev.id,
        "count": len(items),
        "items": items,
    }


@router.post("/portal/{token}/responses", status_code=status.HTTP_200_OK)
def portal_submit_responses(
    token: str,
    payload: PortalSubmitIn,
    finalize: bool = Query(default=False, description="If true, mark participant as responded."),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    p = _ensure_participant_by_token(db, token)
    ev = _ensure_evaluation(db, p.evaluation_id)

    template_code = (ev.instrument_template_code or "DEFAULT").strip()
    version = int(ev.instrument_version or 1)
    questions = _get_active_questions(db, template_code=template_code, version=version)

    q_by_id = {str(q.id): q for q in questions}
    if not q_by_id:
        raise HTTPException(status_code=400, detail="No active questions found for this evaluation's questionnaire.")

    if not payload.answers:
        raise HTTPException(status_code=400, detail="answers list cannot be empty")

    created = 0
    updated = 0
    skipped = 0

    for ans in payload.answers:
        q = q_by_id.get(str(ans.question_id))
        if not q:
            skipped += 1
            continue

        _validate_answer(q, score=ans.score, comment=ans.comment)

        existing = (
            db.execute(
                select(Response)
                .where(Response.participant_id == p.id)
                .where(Response.question_id == q.id)
            )
            .scalars()
            .first()
        )

        if existing:
            existing.score = ans.score
            existing.comment = ans.comment
            db.add(existing)
            updated += 1
        else:
            db.add(
                Response(
                    evaluation_id=ev.id,
                    participant_id=p.id,
                    question_id=q.id,
                    score=ans.score,
                    comment=ans.comment,
                )
            )
            created += 1

    # finalize: mark participant responded
    if finalize:
        if p.status != "responded":
            p.status = "responded"
            p.responded_at = _utcnow()
            db.add(p)

    db.commit()

    return {
        "evaluation_id": ev.id,
        "participant_id": str(p.id),
        "created": created,
        "updated": updated,
        "skipped_unknown_questions": skipped,
        "finalized": bool(finalize),
        "participant_status": p.status,
    }

"""
app.api.evaluations
-------------------
MVP endpoints for managing evaluations + seeding data.

Why this exists:
- We need real DB rows (questions, participants, responses) so analytics becomes real,
  and report generation becomes evidence-based.

Endpoints (MVP):
- POST /api/v1/evaluations                          -> create an evaluation (consultant)
- GET  /api/v1/evaluations                          -> list evaluations
- GET  /api/v1/evaluations/{evaluation_id}          -> get evaluation details

- POST /api/v1/evaluations/{evaluation_id}/participants/invite -> invite participants (consultant)
- GET  /api/v1/evaluations/{evaluation_id}/participants        -> list participants

- POST /api/v1/evaluations/{evaluation_id}/seed/questions
- POST /api/v1/evaluations/{evaluation_id}/seed/demo-responses
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
import uuid

from app.db.session import get_db
from app.db.models import Evaluation, Participant, Question, Response
from sqlalchemy.exc import IntegrityError







router = APIRouter()


# -------------------------
# Helpers
# -------------------------
def _clean_text_for_prompt(text: str, max_chars: int = 20_000) -> str:
    """Trim and lightly normalize source text for prompting."""
    t = (text or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t[:max_chars]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_evaluation_exists(db: Session, evaluation_id: str) -> Evaluation:
    """Raise 404 if evaluation does not exist."""
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {evaluation_id}")
    return ev


def _ensure_demo_evaluation_exists(db: Session, evaluation_id: str) -> Evaluation:
    """
    Ensures an evaluation row exists (MVP convenience).
    Replace later with real create-evaluation flow.
    """
    ev = db.get(Evaluation, evaluation_id)
    if ev:
        return ev

    ev = Evaluation(
        id=evaluation_id,
        tenant_name="Demo Client Plc",
        sector="insurance",
        year=2025,
        regulators={"items": ["NAICOM", "FRC"]},
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _get_active_questions(db: Session, template_code: str, version: int) -> List[Question]:
    return (
        db.execute(
            select(Question)
            .where(Question.template_code == template_code)
            .where(Question.version == version)
        )
        .scalars()
        .all()
    )


from langchain.chat_models import init_chat_model
import os

import os
from dotenv import load_dotenv, find_dotenv

# ---------- Env / defaults ----------

load_dotenv(find_dotenv(), override=True)

#@lru_cache(maxsize=1)
def _get_llm():
    """
    Create and cache the LLM client so we don't re-init on every request.
    Uses your existing OpenAI init_chat_model pattern.
    """
    chosen_model = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required for real LLM calls.")

    return init_chat_model(
        chosen_model,
        model_provider="openai",
        api_key=api_key,
        temperature=0,
    )


async def _generate_json_from_llm(prompt: str) -> Dict[str, Any]:
    """
    Call the LLM and force a JSON object back.
    Returns parsed dict. Raises if parsing fails.
    """
    llm = _get_llm()

    # LangChain chat models usually support ainvoke.
    # Some wrappers return an AIMessage with `.content`.
    resp = await llm.ainvoke(prompt)
    content = getattr(resp, "content", resp)

    if not isinstance(content, str):
        # Worst case: cast to string
        content = str(content)

    # Often models wrap JSON in ```json ... ```
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        # remove optional "json" label on first line
        lines = content.splitlines()
        if lines and lines[0].strip().lower() == "json":
            content = "\n".join(lines[1:]).strip()

    return json.loads(content)

# -------------------------
# Models (API schemas)
# -------------------------

class CreateEvaluationRequest(BaseModel):
    """
    Consultant creates an evaluation (client + year + sector + regulators).
    evaluation_id is optional; if omitted we generate one.
    """
    evaluation_id: Optional[str] = None
    tenant_name: str
    sector: str
    year: int
    regulators: List[str] = Field(default_factory=list)


class EvaluationResponse(BaseModel):
    evaluation_id: str
    tenant_name: str
    sector: str
    year: int
    regulators: List[str]


class InviteParticipantItem(BaseModel):
    email: str
    full_name: Optional[str] = None
    role: Optional[str] = None


class InviteParticipantsRequest(BaseModel):
    participants: List[InviteParticipantItem]


class CreateQuestionRequest(BaseModel):
    template_code: str = "DEFAULT"
    version: int = 1
    dimension: str
    text: str
    answer_type: str = "rating"   # rating | yesno | comment
    weight: int = 1
    active: int = 1               # keep int for DB compatibility


class UpdateQuestionRequest(BaseModel):
    dimension: Optional[str] = None
    text: Optional[str] = None
    answer_type: Optional[str] = None
    weight: Optional[int] = None
    active: Optional[int] = None


class ToggleQuestionActiveRequest(BaseModel):
    active: bool

#from pydantic import BaseModel, Field

class SetInstrumentRequest(BaseModel):
    template_code: str = Field(default="DEFAULT", min_length=1)
    version: int = Field(default=1, ge=1, le=10_000)

# -------------------------
# Consultant: Evaluations CRUD (MVP)
# -------------------------

@router.post("/evaluations", status_code=status.HTTP_201_CREATED)
def create_evaluation(
    payload: CreateEvaluationRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Create a new evaluation row.

    Notes:
    - If evaluation_id isn't provided, we generate eval-<8chars>.
    - Regulators are stored as {"items": [...]} to match your existing model usage.
    """
    evaluation_id = (payload.evaluation_id or "").strip()
    if not evaluation_id:
        evaluation_id = f"eval-{str(uuid4())[:8]}"

    existing = db.get(Evaluation, evaluation_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Evaluation already exists: {evaluation_id}")

    ev = Evaluation(
        id=evaluation_id,
        tenant_name=payload.tenant_name,
        sector=payload.sector,
        year=int(payload.year),
        regulators={"items": list(payload.regulators or [])},
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    return {
        "evaluation_id": ev.id,
        "tenant_name": ev.tenant_name,
        "sector": ev.sector,
        "year": ev.year,
        "regulators": (ev.regulators or {}).get("items", []) if isinstance(ev.regulators, dict) else [],
    }


@router.get("/evaluations", status_code=status.HTTP_200_OK)
def list_evaluations(db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = db.execute(select(Evaluation).order_by(Evaluation.created_at.desc())).scalars().all()
    items = []
    for ev in rows:
        items.append(
            {
                "evaluation_id": ev.id,
                "tenant_name": ev.tenant_name,
                "sector": ev.sector,
                "year": ev.year,
                "regulators": (ev.regulators or {}).get("items", []) if isinstance(ev.regulators, dict) else [],
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
        )
    return {"count": len(items), "items": items}


@router.get("/evaluations/{evaluation_id}", status_code=status.HTTP_200_OK)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _ensure_evaluation_exists(db, evaluation_id)
    return {
        "evaluation_id": ev.id,
        "tenant_name": ev.tenant_name,
        "sector": ev.sector,
        "year": ev.year,
        "regulators": (ev.regulators or {}).get("items", []) if isinstance(ev.regulators, dict) else [],
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


# -------------------------
# Consultant: Participants
# -------------------------

@router.post(
    "/evaluations/{evaluation_id}/participants/invite",
    status_code=status.HTTP_201_CREATED,
)
def invite_participants(
    evaluation_id: str,
    payload: InviteParticipantsRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Invite participants for an evaluation (creates Participant rows).

    Idempotent by (evaluation_id + email):
    - if a participant already exists, we don't create a duplicate.
    """
    _ensure_evaluation_exists(db, evaluation_id)

    if not payload.participants:
        raise HTTPException(status_code=400, detail="participants list cannot be empty")

    created = 0
    skipped_existing = 0

    for item in payload.participants:
        email = (item.email or "").strip().lower()
        if not email:
            continue

        existing = (
            db.execute(
                select(Participant)
                .where(Participant.evaluation_id == evaluation_id)
                .where(Participant.email == email)
            )
            .scalars()
            .first()
        )
        if existing:
            skipped_existing += 1
            continue

        p = Participant(
            evaluation_id=evaluation_id,
            email=email,
            full_name=item.full_name,
            role=item.role,
            status="invited",
            invited_at=_utcnow(),
        )
        db.add(p)
        created += 1

    db.commit()

    return {
        "evaluation_id": evaluation_id,
        "created": created,
        "skipped_existing": skipped_existing,
        "total_now": db.execute(
            select(Participant).where(Participant.evaluation_id == evaluation_id)
        ).scalars().all().__len__(),
    }


@router.get(
    "/evaluations/{evaluation_id}/participants",
    status_code=status.HTTP_200_OK,
)
def list_participants(
    evaluation_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _ensure_evaluation_exists(db, evaluation_id)

    rows = (
        db.execute(
            select(Participant)
            .where(Participant.evaluation_id == evaluation_id)
            .order_by(Participant.created_at.asc())
        )
        .scalars()
        .all()
    )

    items = []
    for p in rows:
        items.append(
            {
                "participant_id": str(p.id),
                "email": p.email,
                "full_name": p.full_name,
                "role": p.role,
                "status": p.status,
                "invited_at": p.invited_at.isoformat() if p.invited_at else None,
                "responded_at": p.responded_at.isoformat() if p.responded_at else None,
            }
        )

    return {"evaluation_id": evaluation_id, "count": len(items), "items": items}




# -------------------------
# Consultant: Questions
# -------------------------

#List questions
@router.get(
    "/evaluations/{evaluation_id}/questions",
    status_code=status.HTTP_200_OK,
)
def list_questions(
    evaluation_id: str,
    template_code: str = "DEFAULT",
    version: int = 1,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _ensure_evaluation_exists(db, evaluation_id)

    rows = (
        db.execute(
            select(Question)
            .where(Question.template_code == template_code)
            .where(Question.version == version)
            .order_by(Question.created_at.asc())
        )
        .scalars()
        .all()
    )

    items = []
    for q in rows:
        items.append(
            {
                "question_id": str(q.id),
                "template_code": q.template_code,
                "version": q.version,
                "dimension": q.dimension,
                "text": q.text,
                "answer_type": q.answer_type,
                "weight": q.weight,
                "active": int(q.active),
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
        )

    return {
        "evaluation_id": evaluation_id,
        "template_code": template_code,
        "version": version,
        "count": len(items),
        "items": items,
    }



# Create Questions



# ...

@router.post("/evaluations/{evaluation_id}/questions")
def create_question(evaluation_id: str, payload: CreateQuestionRequest, db: Session = Depends(get_db)):
    """
    Create a question for (template_code, version). Idempotent on (template_code, version, text).
    Returns existing question if duplicate.
    """

    # 0) Load evaluation to discover selected instrument
    ev = db.execute(
        select(Evaluation).where(Evaluation.id == evaluation_id)
    ).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    template_code = (payload.template_code or ev.instrument_template_code or "DEFAULT").strip()
    version = int(payload.version or ev.instrument_version or 1)

    text = (payload.text or "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="Question text is required.")

    # 1) Pre-check: if it exists, return it (idempotent behavior)
    existing = db.execute(
        select(Question).where(
            Question.template_code == template_code,
            Question.version == version,
            Question.text == text,
        )
    ).scalar_one_or_none()

    if existing:
        return {
            "created": False,
            "message": "Question already exists for this template/version; returning existing.",
            "question": {
                "question_id": str(existing.id),
                "template_code": existing.template_code,
                "version": existing.version,
                "dimension": existing.dimension,
                "text": existing.text,
                "answer_type": existing.answer_type,
                "weight": existing.weight,
                "active": bool(existing.active),
                "created_at": existing.created_at,
            },
        }

    # 2) Create new
    q = Question(
        template_code=template_code,
        version=version,
        dimension=(payload.dimension or "").strip() or "General",
        text=text,
        answer_type=(payload.answer_type or "rating").strip(),
        weight=int(payload.weight or 1),
        active=1 if getattr(payload, "active", True) else 0,
    )

    db.add(q)

    try:
        db.commit()
        db.refresh(q)
    except IntegrityError:
        # If a race condition happens (two requests at once), handle gracefully
        db.rollback()
        existing2 = db.execute(
            select(Question).where(
                Question.template_code == template_code,
                Question.version == version,
                Question.text == text,
            )
        ).scalar_one_or_none()

        if existing2:
            return {
                "created": False,
                "message": "Question already exists (race condition); returning existing.",
                "question": {
                    "question_id": str(existing2.id),
                    "template_code": existing2.template_code,
                    "version": existing2.version,
                    "dimension": existing2.dimension,
                    "text": existing2.text,
                    "answer_type": existing2.answer_type,
                    "weight": existing2.weight,
                    "active": bool(existing2.active),
                    "created_at": existing2.created_at,
                },
            }

        raise HTTPException(status_code=409, detail="Question already exists.")

    return {
        "created": True,
        "message": "Question created.",
        "question": {
            "question_id": str(q.id),
            "template_code": q.template_code,
            "version": q.version,
            "dimension": q.dimension,
            "text": q.text,
            "answer_type": q.answer_type,
            "weight": q.weight,
            "active": bool(q.active),
            "created_at": q.created_at,
        },
    }


from typing import Optional, Any, Dict
from sqlalchemy import select
from fastapi import Query

@router.get("/evaluations/{evaluation_id}/questions", status_code=200)
def list_questions(
    evaluation_id: str,
    template_code: str = Query(default="DEFAULT"),
    version: int = Query(default=1, ge=1),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List questions for a given (template_code, version).
    Optional: active_only=true filters out inactive questions.
    """
    _ensure_evaluation_exists(db, evaluation_id)

    tc = (template_code or "DEFAULT").strip()
    v = int(version or 1)

    stmt = (
        select(Question)
        .where(Question.template_code == tc)
        .where(Question.version == v)
        .order_by(Question.dimension.asc(), Question.created_at.asc())
    )

    if active_only:
        stmt = stmt.where(Question.active == 1)

    rows = db.execute(stmt).scalars().all()

    items = []
    for q in rows:
        items.append(
            {
                "question_id": str(q.id),
                "template_code": q.template_code,
                "version": q.version,
                "dimension": q.dimension,
                "text": q.text,
                "answer_type": q.answer_type,
                "weight": q.weight,
                "active": bool(q.active),
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
        )

    return {
        "evaluation_id": evaluation_id,
        "template_code": tc,
        "version": v,
        "active_only": active_only,
        "count": len(items),
        "items": items,
    }


#Update Question (activate/deactivate/edit)
@router.patch(
    "/questions/{question_id}",
    status_code=status.HTTP_200_OK,
)
def update_question(
    question_id: str,
    payload: UpdateQuestionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    # Question.id is UUID in DB
    try:
        q_uuid = uuid.UUID(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question_id (must be UUID)")

    q = db.get(Question, q_uuid)
    if not q:
        raise HTTPException(status_code=404, detail=f"Question not found: {question_id}")

    if payload.dimension is not None:
        q.dimension = payload.dimension.strip()
    if payload.text is not None:
        q.text = payload.text.strip()
    if payload.answer_type is not None:
        q.answer_type = payload.answer_type.strip().lower()
    if payload.weight is not None:
        q.weight = int(payload.weight)
    if payload.active is not None:
        q.active = int(payload.active)

    db.commit()
    db.refresh(q)

    return {
        "question_id": str(q.id),
        "template_code": q.template_code,
        "version": q.version,
        "dimension": q.dimension,
        "text": q.text,
        "answer_type": q.answer_type,
        "weight": q.weight,
        "active": int(q.active),
    }




@router.get("/evaluations/{evaluation_id}/questions")
def list_questions_for_evaluation(
    evaluation_id: str,
    template_code: str | None = None,
    version: int | None = None,
    db: Session = Depends(get_db),
):
    ev = db.execute(
        select(Evaluation).where(Evaluation.id == evaluation_id)
    ).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    tcode = (template_code or ev.instrument_template_code or "DEFAULT").strip()
    ver = int(version or ev.instrument_version or 1)

    items = db.execute(
        select(Question).where(
            Question.template_code == tcode,
            Question.version == ver,
        ).order_by(Question.created_at.asc())
    ).scalars().all()

    return {
        "evaluation_id": evaluation_id,
        "template_code": tcode,
        "version": ver,
        "count": len(items),
        "items": [
            {
                "question_id": str(q.id),
                "template_code": q.template_code,
                "version": q.version,
                "dimension": q.dimension,
                "text": q.text,
                "answer_type": q.answer_type,
                "weight": q.weight,
                "active": bool(q.active),
                "created_at": q.created_at,
            }
            for q in items
        ],
    }

# -------------------------
# Toggle Questions:  Activate/deactivate a question without deleting it.
# -------------------------



@router.patch("/questions/{question_id}")
def toggle_question_active(
    question_id: str,
    payload: ToggleQuestionActiveRequest,
    db: Session = Depends(get_db),
):
    """
    Activate/deactivate a question without deleting it.
    Sets Question.active (int) to 1 or 0.

    Endpoint: PATCH /api/v1/questions/{question_id}
    Body: { "active": true/false }
    """

    # Question.id is UUID in DB, so SQLAlchemy can accept UUID string.
    q = db.execute(select(Question).where(Question.id == question_id)).scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found.")

    q.active = 1 if payload.active else 0

    try:
        db.commit()
        db.refresh(q)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Update failed due to a constraint error.")

    return {
        "updated": True,
        "message": "Question updated.",
        "question": {
            "question_id": str(q.id),
            "template_code": q.template_code,
            "version": q.version,
            "dimension": q.dimension,
            "text": q.text,
            "answer_type": q.answer_type,
            "weight": q.weight,
            "active": bool(q.active),
            "created_at": q.created_at,
        },
    }



from fastapi import APIRouter, UploadFile, File, Form, Body, HTTPException
from typing import Optional, Dict, Any
import json

#router = APIRouter(prefix="/evaluations", tags=["evaluations"])

def _parse_json_form_field(value: Optional[str], default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default

#@router.post("/{evaluation_id}/questionnaire/generate")
from fastapi import Request
@router.post("/evaluations/{evaluation_id}/questionnaire/generate")
async def questionnaire_generate(
    evaluation_id: str,
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    n_questions: Optional[int] = Form(default=None),
    template_code: Optional[str] = Form(default=None),
    version: Optional[int] = Form(default=None),
    allowed_answer_types: Optional[str] = Form(default=None),
    dimension_hints: Optional[str] = Form(default=None),
    body: Optional[Dict[str, Any]] = Body(default=None),
):
    """
    Accepts:
      - multipart: file + fields
      - JSON: { source_text, n_questions, template_code, version, allowed_answer_types, dimension_hints }

    Returns:
      { items: [{dimension,text,answer_type,weight,active}, ...], meta: {...} }
    """

    # -------------------------
    # 1) Parse input (multipart or JSON)
    # -------------------------
    if file is None:
        # JSON mode
        if not body:
            raise HTTPException(status_code=400, detail="Provide multipart file or JSON body with source_text.")
        source_text = (body.get("source_text") or "").strip()
        if not source_text:
            raise HTTPException(status_code=400, detail="source_text is required.")
        n = int(body.get("n_questions") or 10)
        t = str(body.get("template_code") or "DEFAULT").strip()
        v = int(body.get("version") or 1)
        allowed = body.get("allowed_answer_types") or ["rating", "yesno", "comment"]
        hints = body.get("dimension_hints") or []
    else:
        filename = (file.filename or "").lower()

        if filename.endswith(".doc"):
            raise HTTPException(status_code=415, detail="Unsupported .doc. Please upload .docx or .pdf (or convert to .txt).")

        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        # For now, support plain text-ish only
        if filename.endswith(".txt") or filename.endswith(".md") or filename.endswith(".markdown"):
            source_text = raw.decode("utf-8", errors="ignore").strip()
        else:
            # You can add PDF/DOCX extraction later
            raise HTTPException(status_code=501, detail="File extraction not implemented yet. Upload .txt for now.")

        n = int(n_questions or 10)
        t = str(template_code or "DEFAULT").strip()
        v = int(version or 1)
        allowed = _parse_json_form_field(allowed_answer_types, ["rating", "yesno", "comment"])
        hints = _parse_json_form_field(dimension_hints, [])

    n = max(1, min(int(n), 50))
    source_text = _clean_text_for_prompt(source_text)

    # -------------------------
    # 2) Call LLM (or fall back)
    # -------------------------
    # IMPORTANT: Reuse whatever LLM setup you already have (since /api/v1/llm/sanity exists).
    # Here we assume you have something like app.llm.client.get_llm() or similar.
    # If you DON'T, I include a safe deterministic fallback below.

    try:
        # ---- PROMPT ----
        # We ask for strict JSON output so the UI can render immediately.
        dim_hint_str = ", ".join(hints) if hints else "Board Composition, Risk Oversight, Strategy Oversight, Board Culture & Dynamics, Open Comments"

        prompt = f"""
            You are an expert board evaluation consultant.
            
            Generate {n} questionnaire questions from the SOURCE TEXT.
            Rules:
            - Output MUST be valid JSON only (no markdown, no commentary).
            - Output schema:
              {{
                "items": [
                  {{
                    "dimension": "string",
                    "text": "string",
                    "answer_type": "rating|yesno|comment",
                    "weight": 1,
                    "active": true
                  }}
                ]
              }}
            - Keep questions specific and grounded in the SOURCE TEXT.
            - Use these dimension hints where possible: {dim_hint_str}
            - Allowed answer types: {allowed}
            - Make the questions professional and suitable for a board evaluation.
            
            SOURCE TEXT:
            {source_text}
            """.strip()

        # ---- CALL YOUR LLM ----
        # Replace the following two lines with your actual LLM call.
        # Example patterns:
        llm =  _get_llm()
        raw = await llm.invoke(prompt)

        if not raw:
            raise RuntimeError("LLM generator not wired yet (app.llm.provider.generate_text missing).")

        # raw might be dict already or string
        if isinstance(raw, dict):
            llm_json = raw
        else:
            llm_json = json.loads(raw)

        items = llm_json.get("items") or []
        if not isinstance(items, list) or not items:
            raise ValueError("LLM returned no items.")

    except Exception as e:
        # -------------------------
        # 3) Fallback: deterministic “real-ish” extraction
        # -------------------------
        # This will create meaningful questions based on sentences/keywords,
        # so demo works even before LLM wiring is finished.
        text_lower = source_text.lower()
        base_dimension = hints[0] if hints else "Board Composition"

        def pick_dimension(q: str) -> str:
            ql = q.lower()
            if "risk" in ql or "cyber" in ql or "compliance" in ql:
                return "Risk Oversight"
            if "strategy" in ql or "performance" in ql or "kpi" in ql:
                return "Strategy Oversight"
            if "culture" in ql or "minutes" in ql or "meeting" in ql:
                return "Board Culture & Dynamics"
            return base_dimension

        candidates = []
        for line in re.split(r"[.\n]+", source_text):
            s = line.strip()
            if len(s) < 40:
                continue
            candidates.append(s)

        # If no candidates, just use generic but *non-stub* questions
        if not candidates:
            candidates = [
                "The board receives timely, relevant and accurate information to enable effective oversight.",
                "The board demonstrates sufficient independence and diversity to challenge management decisions.",
                "The board actively oversees key enterprise risks, including regulatory and emerging risks.",
                "The board monitors execution against strategy using clear KPIs and effective governance processes.",
                "Board discussions encourage constructive challenge, candour, and healthy debate.",
            ]

        items = []
        for i in range(n):
            seed = candidates[i % len(candidates)]
            q_text = f"To what extent does the board ensure that: {seed}?"
            a_type = "rating" if "rating" in allowed else (allowed[0] if allowed else "rating")
            dim = pick_dimension(seed)
            items.append({"dimension": dim, "text": q_text, "answer_type": a_type, "weight": 1, "active": True})

    return {
        "items": items,
        "meta": {"evaluation_id": evaluation_id, "template_code": t, "version": v},
    }



# Reuse your existing get_db, Evaluation, Question imports

class BulkQuestionItem(BaseModel):
    dimension: str = Field(default="General", min_length=1)
    text: str = Field(min_length=1)
    answer_type: str = Field(default="rating")  # rating|yesno|comment
    weight: int = Field(default=1, ge=1, le=100)
    active: bool = Field(default=True)

class BulkCreateQuestionsRequest(BaseModel):
    template_code: str = Field(default="DEFAULT", min_length=1)
    version: int = Field(default=1, ge=1, le=10_000)
    items: List[BulkQuestionItem] = Field(default_factory=list)


@router.post("/evaluations/{evaluation_id}/questions/bulk")
def bulk_create_questions(
    evaluation_id: str,
    payload: BulkCreateQuestionsRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Bulk add questions to (template_code, version).
    Idempotent on (template_code, version, text).
    Returns created / skipped_existing counts.
    """
    # Ensure evaluation exists
    ev = db.execute(select(Evaluation).where(Evaluation.id == evaluation_id)).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    tc = (payload.template_code or ev.instrument_template_code or "DEFAULT").strip()
    ver = int(payload.version or ev.instrument_version or 1)

    if not payload.items:
        raise HTTPException(status_code=400, detail="items cannot be empty")

    created = 0
    skipped_existing = 0
    errors: List[Dict[str, Any]] = []

    for idx, item in enumerate(payload.items):
        text = (item.text or "").strip()
        if not text:
            errors.append({"index": idx, "error": "empty text"})
            continue

        # idempotent check
        existing = db.execute(
            select(Question).where(
                Question.template_code == tc,
                Question.version == ver,
                Question.text == text,
            )
        ).scalar_one_or_none()

        if existing:
            skipped_existing += 1
            continue

        q = Question(
            template_code=tc,
            version=ver,
            dimension=(item.dimension or "General").strip() or "General",
            text=text,
            answer_type=(item.answer_type or "rating").strip().lower(),
            weight=int(item.weight or 1),
            active=1 if item.active else 0,
        )

        db.add(q)
        try:
            db.flush()  # catch constraints early
            created += 1
        except IntegrityError as e:
            db.rollback()
            skipped_existing += 1  # treat as duplicate/race
        except Exception as e:
            db.rollback()
            errors.append({"index": idx, "error": str(e)})

    db.commit()

    return {
        "evaluation_id": evaluation_id,
        "template_code": tc,
        "version": ver,
        "created": created,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }

# -------------------------
# Seed: Questions
# -------------------------

@router.post(
    "/evaluations/{evaluation_id}/seed/questions",
    status_code=status.HTTP_201_CREATED,
)
def seed_questions(
    evaluation_id: str,
    template_code: str = "DEFAULT",
    version: int = 1,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Seed a default set of questions (instrument) into the DB.

    Safe to call multiple times:
    - it checks by (template_code, version, text) and only inserts missing questions.
    """
    #_ensure_demo_evaluation_exists(db, evaluation_id)
    _ensure_evaluation_exists(db, evaluation_id)

    default_questions: List[Dict[str, Any]] = [
        # --- Board Composition ---
        {
            "dimension": "Board Composition",
            "text": "The board has an appropriate mix of skills, experience, and independence to oversee the organisation effectively.",
            "answer_type": "rating",
            "weight": 1,
        },
        {
            "dimension": "Board Composition",
            "text": "Board succession planning is proactive and aligned to future strategic needs.",
            "answer_type": "rating",
            "weight": 1,
        },

        # --- Risk Oversight ---
        {
            "dimension": "Risk Oversight",
            "text": "The board provides effective oversight of key enterprise risks (financial, operational, regulatory).",
            "answer_type": "rating",
            "weight": 1,
        },
        {
            "dimension": "Risk Oversight",
            "text": "The board actively oversees emerging risks, including technology and cyber risks.",
            "answer_type": "rating",
            "weight": 1,
        },

        # --- Strategy Oversight ---
        {
            "dimension": "Strategy Oversight",
            "text": "The board provides robust challenge and guidance on strategy, performance, and value creation.",
            "answer_type": "rating",
            "weight": 1,
        },
        {
            "dimension": "Strategy Oversight",
            "text": "The board monitors execution against strategy using clear KPIs and timely reporting.",
            "answer_type": "rating",
            "weight": 1,
        },

        # --- Culture & Dynamics ---
        {
            "dimension": "Board Culture & Dynamics",
            "text": "Board discussions encourage constructive challenge, candour, and healthy debate.",
            "answer_type": "rating",
            "weight": 1,
        },
        {
            "dimension": "Board Culture & Dynamics",
            "text": "Board papers and meeting minutes are well-structured and support effective decision-making.",
            "answer_type": "rating",
            "weight": 1,
        },

        # --- Optional comment prompts ---
        {
            "dimension": "Open Comments",
            "text": "What are the board’s top 3 governance strengths?",
            "answer_type": "comment",
            "weight": 1,
        },
        {
            "dimension": "Open Comments",
            "text": "What are the board’s top 3 governance weaknesses / improvement areas?",
            "answer_type": "comment",
            "weight": 1,
        },
    ]

    existing = _get_active_questions(db, template_code=template_code, version=version)
    existing_texts = set((q.text or "").strip() for q in existing)

    created = 0
    for q in default_questions:
        if q["text"].strip() in existing_texts:
            continue
        db.add(
            Question(
                template_code=template_code,
                version=version,
                dimension=q["dimension"],
                text=q["text"],
                answer_type=q["answer_type"],
                weight=int(q.get("weight", 1)),
                active=1,
            )
        )
        created += 1

    db.commit()

    total = len(_get_active_questions(db, template_code=template_code, version=version))
    return {
        "evaluation_id": evaluation_id,
        "template_code": template_code,
        "version": version,
        "created": created,
        "total_questions_now": total,
    }


#from fastapi import HTTPException
#from sqlalchemy import select

@router.patch("/evaluations/{evaluation_id}/instrument")
def set_evaluation_instrument(
    evaluation_id: str,
    payload: SetInstrumentRequest,
    db: Session = Depends(get_db),
):
    template_code = (payload.template_code or "DEFAULT").strip()
    version = int(payload.version or 1)

    ev = db.execute(
        select(Evaluation).where(Evaluation.id == evaluation_id)
    ).scalar_one_or_none()

    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    ev.instrument_template_code = template_code
    ev.instrument_version = version

    db.commit()
    db.refresh(ev)

    return {
        "updated": True,
        "evaluation_id": ev.id,
        "instrument": {
            "template_code": ev.instrument_template_code,
            "version": ev.instrument_version,
        },
    }


# -------------------------
# Seed: Participants + Responses
# -------------------------

@router.post(
    "/evaluations/{evaluation_id}/seed/demo-responses",
    status_code=status.HTTP_201_CREATED,
)
def seed_demo_responses(
    evaluation_id: str,
    template_code: str = "DEFAULT",
    version: int = 1,
    invited: int = 12,
    responded: int = 10,
    random_seed: int = 42,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Seed demo participants + responses to generate meaningful analytics.

    Safe-ish to call multiple times:
    - Participants are created if missing (by evaluation_id + email).
    - Responses are only created if missing (UniqueConstraint participant_id + question_id).
    """
    if responded > invited:
        raise HTTPException(status_code=400, detail="responded cannot be greater than invited")

    _ensure_evaluation_exists(db, evaluation_id)

    questions = _get_active_questions(db, template_code=template_code, version=version)
    if not questions:
        raise HTTPException(
            status_code=400,
            detail="No questions found. Call seed/questions first.",
        )

    rnd = random.Random(random_seed)

    # Create participants
    roles = ["Chair", "INED", "INED", "ED", "ED", "Company Secretary"]
    created_participants = 0
    participants: List[Participant] = []

    for i in range(invited):
        email = f"board_member_{i+1:02d}@demo-client.test"

        existing_p = (
            db.execute(
                select(Participant)
                .where(Participant.evaluation_id == evaluation_id)
                .where(Participant.email == email)
            )
            .scalars()
            .first()
        )

        if existing_p:
            participants.append(existing_p)
            continue

        p = Participant(
            evaluation_id=evaluation_id,
            email=email,
            full_name=f"Board Member {i+1:02d}",
            role=roles[i % len(roles)],
            status="invited",
            invited_at=_utcnow(),
        )
        db.add(p)
        db.flush()  # assign id
        participants.append(p)
        created_participants += 1

    db.commit()

    # Mark first "responded" participants as responded and create responses
    rating_questions = [q for q in questions if q.answer_type == "rating"]
    comment_questions = [q for q in questions if q.answer_type == "comment"]

    created_responses = 0
    updated_participants = 0

    for idx, p in enumerate(participants):
        if idx < responded:
            if p.status != "responded":
                p.status = "responded"
                p.responded_at = _utcnow()
                updated_participants += 1

            # rating responses: skew slightly positive but leave weaknesses in Risk Oversight
            for q in rating_questions:
                base = rnd.choices([2, 3, 4, 5], weights=[5, 25, 45, 25])[0]

                if q.dimension == "Risk Oversight":
                    base = max(2, base - 1)

                exists = (
                    db.execute(
                        select(Response)
                        .where(Response.participant_id == p.id)
                        .where(Response.question_id == q.id)
                    )
                    .scalars()
                    .first()
                )
                if exists:
                    continue

                db.add(
                    Response(
                        evaluation_id=evaluation_id,
                        participant_id=p.id,
                        question_id=q.id,
                        score=int(base),
                        comment=None,
                    )
                )
                created_responses += 1

            # comment responses: only 3 of the responded participants provide comments (MVP realism)
            if idx < 3 and comment_questions:
                strengths_text = (
                    "Board meetings are well-structured and adequately documented. "
                    "Independent directors demonstrate robust challenge and debate. "
                    "Committees provide clear oversight and escalate matters appropriately."
                )
                weaknesses_text = (
                    "Limited board-level oversight of emerging technology and cyber risks. "
                    "CEO performance evaluation and succession planning not fully formalized. "
                    "Risk appetite statements not consistently reviewed and documented annually."
                )

                for q in comment_questions:
                    exists = (
                        db.execute(
                            select(Response)
                            .where(Response.participant_id == p.id)
                            .where(Response.question_id == q.id)
                        )
                        .scalars()
                        .first()
                    )
                    if exists:
                        continue

                    comment = strengths_text if "strength" in q.text.lower() else weaknesses_text
                    db.add(
                        Response(
                            evaluation_id=evaluation_id,
                            participant_id=p.id,
                            question_id=q.id,
                            score=None,
                            comment=comment,
                        )
                    )
                    created_responses += 1

    db.commit()

    return {
        "evaluation_id": evaluation_id,
        "template_code": template_code,
        "version": version,
        "participants_created": created_participants,
        "participants_marked_responded": updated_participants,
        "responses_created": created_responses,
        "invited": invited,
        "responded": responded,
    }

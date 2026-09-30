"""
Long-format export of evaluation responses (CSV / XLSX) and JSON listing.

Filters align with consultant workflows: assignment, assignment_type, track template code,
and optional question bank (template_code + version).
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    AssessmentAssignment,
    AssessmentTrackTemplate,
    Evaluation,
    EvaluationTrack,
    Participant,
    Question,
    Response,
)


def _n(s: Optional[str]) -> str:
    return (s or "").strip()


def _pick_instrument_for_track(ev: Evaluation, tpl: AssessmentTrackTemplate, et: EvaluationTrack) -> Dict[str, Any]:
    tcode = _n(et.instrument_template_code) or _n(tpl.default_template_code) or _n(ev.instrument_template_code) or "DEFAULT"
    ver = et.instrument_version if et.instrument_version is not None else (tpl.default_version or ev.instrument_version or 1)
    return {"template_code": tcode, "version": int(ver)}


def _resolve_track_filter(db: Session, evaluation_id: str, track_code: str, ev: Evaluation) -> Tuple[str, str, int]:
    c = _n(track_code)
    if not c:
        raise HTTPException(status_code=400, detail="track_code is required when filtering by track.")

    tpl = (
        db.execute(select(AssessmentTrackTemplate).where(AssessmentTrackTemplate.code == c))
        .scalars()
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Unknown track code: {c}")

    et = (
        db.execute(
            select(EvaluationTrack)
            .where(EvaluationTrack.evaluation_id == evaluation_id)
            .where(EvaluationTrack.track_template_id == tpl.id)
        )
        .scalars()
        .first()
    )
    if not et:
        raise HTTPException(status_code=404, detail=f"Track '{c}' is not configured for this evaluation.")

    inst = _pick_instrument_for_track(ev, tpl, et)
    atype = _n(tpl.assignment_type) or _n(tpl.code)
    return atype, inst["template_code"], int(inst["version"])


EXPORT_COLUMNS = [
    "response_id",
    "evaluation_id",
    "assignment_id",
    "assignment_type",
    "committee_name",
    "assignment_status",
    "respondent_participant_id",
    "respondent_email",
    "respondent_full_name",
    "respondent_role",
    "subject_participant_id",
    "subject_email",
    "subject_full_name",
    "subject_role",
    "question_id",
    "question_template_code",
    "question_version",
    "dimension",
    "question_text",
    "answer_type",
    "score",
    "comment",
    "response_created_at",
]


def _row_from_orm(
    r: Response,
    q: Question,
    respondent: Participant,
    assignment: Optional[AssessmentAssignment],
    subject: Optional[Participant],
) -> Dict[str, Any]:
    return {
        "response_id": str(r.id),
        "evaluation_id": r.evaluation_id,
        "assignment_id": str(r.assignment_id) if r.assignment_id else None,
        "assignment_type": assignment.assignment_type if assignment else None,
        "committee_name": assignment.committee_name if assignment else None,
        "assignment_status": assignment.status if assignment else None,
        "respondent_participant_id": str(respondent.id),
        "respondent_email": respondent.email,
        "respondent_full_name": respondent.full_name,
        "respondent_role": respondent.role,
        "subject_participant_id": str(subject.id) if subject else None,
        "subject_email": subject.email if subject else None,
        "subject_full_name": subject.full_name if subject else None,
        "subject_role": subject.role if subject else None,
        "question_id": str(q.id),
        "question_template_code": q.template_code,
        "question_version": int(q.version or 1),
        "dimension": q.dimension,
        "question_text": q.text,
        "answer_type": q.answer_type,
        "score": r.score,
        "comment": r.comment,
        "response_created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _build_select(
    evaluation_id: str,
    *,
    assignment_id: Optional[UUID],
    assignment_type: Optional[str],
    track_filter: Optional[Tuple[str, str, int]],
    question_template_code: Optional[str],
    question_version: Optional[int],
):
    SubjectP = aliased(Participant)
    stmt = (
        select(Response, Question, Participant, AssessmentAssignment, SubjectP)
        .join(Question, Response.question_id == Question.id)
        .join(Participant, Response.participant_id == Participant.id)
        .outerjoin(AssessmentAssignment, Response.assignment_id == AssessmentAssignment.id)
        .outerjoin(SubjectP, AssessmentAssignment.subject_participant_id == SubjectP.id)
        .where(Response.evaluation_id == evaluation_id)
    )

    if assignment_id:
        stmt = stmt.where(Response.assignment_id == assignment_id)
    if assignment_type:
        stmt = stmt.where(AssessmentAssignment.assignment_type == assignment_type.strip())
    if track_filter:
        atype, tc, ver = track_filter
        stmt = stmt.where(AssessmentAssignment.assignment_type == atype)
        stmt = stmt.where(AssessmentAssignment.instrument_template_code == tc)
        stmt = stmt.where(AssessmentAssignment.instrument_version == ver)
    if question_template_code:
        stmt = stmt.where(Question.template_code == question_template_code.strip())
    if question_version is not None:
        stmt = stmt.where(Question.version == int(question_version))

    stmt = stmt.order_by(Response.created_at.asc(), Response.id.asc())
    return stmt


def _build_count_select(
    evaluation_id: str,
    *,
    assignment_id: Optional[UUID],
    assignment_type: Optional[str],
    track_filter: Optional[Tuple[str, str, int]],
    question_template_code: Optional[str],
    question_version: Optional[int],
):
    SubjectP = aliased(Participant)
    stmt = (
        select(func.count(Response.id))
        .select_from(Response)
        .join(Question, Response.question_id == Question.id)
        .join(Participant, Response.participant_id == Participant.id)
        .outerjoin(AssessmentAssignment, Response.assignment_id == AssessmentAssignment.id)
        .outerjoin(SubjectP, AssessmentAssignment.subject_participant_id == SubjectP.id)
        .where(Response.evaluation_id == evaluation_id)
    )
    if assignment_id:
        stmt = stmt.where(Response.assignment_id == assignment_id)
    if assignment_type:
        stmt = stmt.where(AssessmentAssignment.assignment_type == assignment_type.strip())
    if track_filter:
        atype, tc, ver = track_filter
        stmt = stmt.where(AssessmentAssignment.assignment_type == atype)
        stmt = stmt.where(AssessmentAssignment.instrument_template_code == tc)
        stmt = stmt.where(AssessmentAssignment.instrument_version == ver)
    if question_template_code:
        stmt = stmt.where(Question.template_code == question_template_code.strip())
    if question_version is not None:
        stmt = stmt.where(Question.version == int(question_version))
    return stmt


def fetch_response_rows(
    db: Session,
    evaluation_id: str,
    ev: Evaluation,
    *,
    assignment_id: Optional[str] = None,
    assignment_type: Optional[str] = None,
    track_code: Optional[str] = None,
    question_template_code: Optional[str] = None,
    question_version: Optional[int] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    aid: Optional[UUID] = None
    if assignment_id:
        try:
            aid = UUID(str(assignment_id).strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid assignment_id (expected UUID).") from e

    track_filter: Optional[Tuple[str, str, int]] = None
    if track_code:
        track_filter = _resolve_track_filter(db, evaluation_id, track_code, ev)

    stmt = _build_select(
        evaluation_id,
        assignment_id=aid,
        assignment_type=assignment_type,
        track_filter=track_filter,
        question_template_code=question_template_code,
        question_version=question_version,
    )
    count_stmt = _build_count_select(
        evaluation_id,
        assignment_id=aid,
        assignment_type=assignment_type,
        track_filter=track_filter,
        question_template_code=question_template_code,
        question_version=question_version,
    )

    total = int(db.execute(count_stmt).scalar_one() or 0)

    if limit is not None:
        stmt = stmt.offset(max(offset, 0)).limit(limit)

    rows = db.execute(stmt).all()
    items = [_row_from_orm(r, q, resp, asn, subj) for r, q, resp, asn, subj in rows]
    return items, total


def responses_to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow([row.get(k, "") for k in EXPORT_COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


def responses_to_xlsx_bytes(rows: List[Dict[str, Any]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "responses"
    ws.append(EXPORT_COLUMNS)
    for row in rows:
        ws.append([row.get(k, "") for k in EXPORT_COLUMNS])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()

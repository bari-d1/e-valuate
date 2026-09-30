"""
app.services.analytics
----------------------
Dynamic analytics computed from stored participants + responses + questions.

Supports optional scoping by assignment / assignment type / track / question bank
(M3 — assignment-aware analytics).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import AssessmentAssignment, Evaluation, Participant, Question, Report, Response

from app.services.response_export import _resolve_track_filter


def _compute_metrics_from_rating_rows(
    rows: List[Tuple[Any, Any, Any]],
) -> Tuple[float, List[Dict[str, Any]], List[str], List[str]]:
    """rows: (dimension, weight, score) for rating responses."""
    agg: Dict[str, Dict[str, float]] = {}
    for dim, weight, score in rows:
        w = float(weight or 1)
        s = float(score or 0)
        if dim not in agg:
            agg[dim] = {"wsum": 0.0, "wtotal": 0.0, "count": 0.0}
        agg[dim]["wsum"] += s * w
        agg[dim]["wtotal"] += w
        agg[dim]["count"] += 1.0

    dimensions: List[Dict[str, Any]] = []
    for dim, a in agg.items():
        avg_1_to_5 = (a["wsum"] / a["wtotal"]) if a["wtotal"] else 0.0
        score_0_to_100 = round((avg_1_to_5 / 5.0) * 100.0, 1)
        dimensions.append({"name": dim, "score": score_0_to_100})

    if rows:
        overall_avg_1_to_5 = sum((float(score) * float(weight or 1)) for _, weight, score in rows) / sum(
            float(weight or 1) for _, weight, _ in rows
        )
        overall_score = round((overall_avg_1_to_5 / 5.0) * 100.0, 1)
    else:
        overall_score = 0.0

    dims_sorted = sorted(dimensions, key=lambda d: d["score"], reverse=True)
    strengths: List[str] = []
    weaknesses: List[str] = []
    for d in dims_sorted[:2]:
        strengths.append(f"Strong performance in {d['name']} (score {d['score']}).")
    for d in sorted(dimensions, key=lambda d: d["score"])[:2]:
        weaknesses.append(f"Improvement needed in {d['name']} (score {d['score']}).")

    return overall_score, dims_sorted, strengths, weaknesses


def build_analytics(
    db: Session,
    evaluation_id: str,
    include_trends: bool = True,
    *,
    assignment_id: Optional[str] = None,
    assignment_type: Optional[str] = None,
    track_code: Optional[str] = None,
    question_template_code: Optional[str] = None,
    question_version: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build analytics for an evaluation based on DB responses.

    Optional filters match GET .../responses export semantics (assignment-aware).

    When any scope filter is set, trend history is omitted (reports are evaluation-wide).
    """
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise ValueError(f"Evaluation not found: {evaluation_id}")

    scoped = any(
        [
            assignment_id,
            assignment_type,
            track_code,
            question_template_code,
            question_version is not None,
        ]
    )
    if scoped:
        include_trends = False

    aid: Optional[UUID] = None
    if assignment_id:
        try:
            aid = UUID(str(assignment_id).strip())
        except ValueError as e:
            raise ValueError("Invalid assignment_id (expected UUID).") from e

    track_filter = None
    if track_code:
        track_filter = _resolve_track_filter(db, evaluation_id, track_code, evaluation)

    invited = db.execute(
        select(Participant).where(Participant.evaluation_id == evaluation_id)
    ).scalars().all()
    invited_count = len(invited)
    responded_count = sum(1 for p in invited if (p.responded_at is not None or p.status == "responded"))
    completion_rate = (responded_count / invited_count) if invited_count else 0.0

    stmt = (
        select(Question.dimension, Question.weight, Response.score)
        .join(Response, Response.question_id == Question.id)
        .outerjoin(AssessmentAssignment, Response.assignment_id == AssessmentAssignment.id)
        .where(Response.evaluation_id == evaluation_id)
        .where(Response.score.is_not(None))
    )

    if aid:
        stmt = stmt.where(Response.assignment_id == aid)
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

    rows = db.execute(stmt).all()
    rating_rows_used = len(rows)

    overall_score, dims_sorted, strengths, weaknesses = _compute_metrics_from_rating_rows(rows)

    trends: Dict[str, Any] = {"available": False, "years": []}
    if include_trends:
        trends = _build_trends_from_reports(db, evaluation)
    elif scoped:
        trends = {
            "available": False,
            "years": [],
            "note": "Trends compare full evaluation reports; omitted when analytics scope filters are applied.",
        }

    scope_filters: Dict[str, Any] = {}
    if assignment_id:
        scope_filters["assignment_id"] = str(assignment_id).strip()
    if assignment_type:
        scope_filters["assignment_type"] = assignment_type.strip()
    if track_code:
        scope_filters["track_code"] = track_code.strip()
    if question_template_code:
        scope_filters["question_template_code"] = question_template_code.strip()
    if question_version is not None:
        scope_filters["question_version"] = int(question_version)

    return {
        "evaluation": {
            "id": evaluation.id,
            "tenant_name": evaluation.tenant_name,
            "year": evaluation.year,
            "sector": evaluation.sector,
            "regulators": (evaluation.regulators or {}).get("items", []),
        },
        "response_stats": {
            "invited": invited_count,
            "responded": responded_count,
            "completion_rate": round(completion_rate, 4),
        },
        "scope": {
            "filters": scope_filters,
            "scoped": scoped,
            "rating_rows_used": rating_rows_used,
        },
        "metrics": {
            "overall_score": overall_score,
            "dimensions": dims_sorted,
        },
        "trends": trends,
        "comments": {
            "strengths": strengths,
            "weaknesses": weaknesses,
        },
    }


def _build_trends_from_reports(db: Session, evaluation: Evaluation) -> Dict[str, Any]:
    """
    MVP trends: use past reports for the same tenant_name across years.

    Why: trends require historical scoring; reports already store computed analytics.
    Later: compute trends directly from responses once historical responses exist.
    """
    evals = db.execute(
        select(Evaluation)
        .where(Evaluation.tenant_name == evaluation.tenant_name)
        .order_by(Evaluation.year.asc())
    ).scalars().all()

    year_scores: List[Dict[str, Any]] = []
    for ev in evals:
        rep = db.execute(
            select(Report)
            .where(Report.evaluation_id == ev.id)
            .order_by(desc(Report.created_at))
            .limit(1)
        ).scalars().first()

        if not rep:
            continue

        try:
            score = (
                (rep.summary_json or {})
                .get("analytics", {})
                .get("metrics", {})
                .get("overall_score", None)
            )
        except Exception:
            score = None

        if score is None:
            continue

        year_scores.append({"year": ev.year, "overall_score": score})

    return {
        "available": len(year_scores) >= 2,
        "years": year_scores,
    }

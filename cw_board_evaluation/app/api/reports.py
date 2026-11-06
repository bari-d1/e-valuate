"""
app.api.reports
---------------
API endpoints related to evaluation reports.

Endpoints:
- POST  /evaluations/{evaluation_id}/report/generate  -> generate + persist a report from the latest
                                                         completed analysis (approved findings only; 409 if none)
- GET   /evaluations/{evaluation_id}/report           -> latest report payload for evaluation (DB)
- GET   /reports/{report_id}                          -> get report by id (DB)
- GET   /reports/{report_id}/docx                     -> export report to DOCX (from DB payload)
- GET   /llm/sanity                                   -> check LLM
- GET   /debug/env                                    -> show env flags (dev)
"""

from __future__ import annotations

import os
import traceback
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.docx_exporter import export_report_to_docx
from app.services.reporting import ReportError, generate_report_for_evaluation, llm_sanity_check
from app.services.report_store import (
    create_report,
    get_report_by_id as db_get_report_by_id,
    get_latest_report_for_evaluation as db_get_latest_report_for_evaluation,
)

router = APIRouter()


# --- Simple auth placeholder (replace later) ---


class CurrentUser(BaseModel):
    """Represents the currently authenticated user (MVP placeholder)."""

    id: str
    email: str
    full_name: str | None = None
    role: str | None = None


def get_current_user() -> CurrentUser:
    """Return a dummy user for MVP/testing."""
    return CurrentUser(
        id="00000000-0000-0000-0000-000000000001",
        email="consultant@example.com",
        full_name="Test Consultant",
        role="consultant",
    )


# --- Request/response models ---


class GenerateReportRequest(BaseModel):
    """
    Request body for triggering report generation. The report is built from the latest completed
    analysis run; older clients still send include_trends / include_compliance, which are ignored.
    """


class GenerateReportResponse(BaseModel):
    """Response payload for report generation."""

    report_id: str
    status: str


# --- Routes ---


@router.post(
    "/evaluations/{evaluation_id}/report/generate",
    response_model=GenerateReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_report_endpoint(
    evaluation_id: str,
    payload: GenerateReportRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GenerateReportResponse:
    """
    Build the report from the latest completed analysis run (approved findings, approved
    conclusions and the evidence they cite) and persist it to Postgres.
    """
    try:
        summary_json = generate_report_for_evaluation(db, evaluation_id, current_user.id)

        # Persist to Postgres
        report = create_report(
            db=db,
            evaluation_id=evaluation_id,
            created_by=current_user.id,
            status="draft",
            summary_json=summary_json,
        )

        # Record the report id with the rest of the traceability
        sj = dict(report.summary_json or {})
        sj["traceability"] = {**(sj.get("traceability") or {}), "report_id": str(report.id)}
        report.summary_json = sj  # IMPORTANT: reassign whole JSON
        db.add(report)
        db.commit()
        db.refresh(report)

        return GenerateReportResponse(report_id=str(report.id), status=report.status)

    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    except ReportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    except Exception as exc:  # noqa: BLE001
        print("[ERROR] Report generation failed:", repr(exc))
        traceback.print_exc()

        if os.getenv("DEBUG_API_ERRORS", "0") == "1":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate report. Please try again later.",
        ) from exc


@router.get("/evaluations/{evaluation_id}/report", status_code=status.HTTP_200_OK)
async def get_latest_report_for_evaluation(
    evaluation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieve the latest report (DB) for a given evaluation.
    """
    report = db_get_latest_report_for_evaluation(db, evaluation_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report found for evaluation_id={evaluation_id}")

    return {
        "report_id": str(report.id),
        "evaluation_id": report.evaluation_id,
        "status": report.status,
        "created_by": report.created_by,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "summary_json": report.summary_json,
    }


@router.get("/reports/{report_id}", status_code=status.HTTP_200_OK)
async def get_report_by_id(
    report_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieve a report payload by report_id (DB-backed).
    """
    report = db_get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")

    return {
        "report_id": str(report.id),
        "evaluation_id": report.evaluation_id,
        "created_by": report.created_by,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "summary_json": report.summary_json,
    }


@router.get("/reports/{report_id}/docx", status_code=status.HTTP_200_OK)
async def download_report_docx(
    report_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate (on-demand) and download the DOCX for a report (from DB payload).
    """
    report = db_get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")

    payload = {
        "report_id": str(report.id),
        "evaluation_id": report.evaluation_id,
        "created_by": report.created_by,
        "status": report.status,
        "summary_json": report.summary_json,
    }

    path = export_report_to_docx(payload)

    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@router.get("/llm/sanity", status_code=status.HTTP_200_OK)
async def llm_sanity() -> Dict[str, Any]:
    """
    Quick check: can we call the configured LLM successfully?
    """
    try:
        result = llm_sanity_check()
        return {"status": "ok", "result": result}
    except Exception as exc:  # noqa: BLE001
        print("[ERROR] LLM sanity check failed:", repr(exc))
        traceback.print_exc()

        if os.getenv("DEBUG_API_ERRORS", "0") == "1":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM sanity check failed.",
        ) from exc


"""
app.api.analysis
----------------
Analysis of assembled evaluations (app.services.analysis). Consultant auth like
the other consultant routes; X-Consultant-Name names who decided what.

- POST  /evaluations/{id}/analysis/runs                         start a run (min_raters, include_unsubmitted, ai)
- GET   /evaluations/{id}/analysis/runs                         runs, newest first
- GET   /evaluations/{id}/analysis/runs/{run_id}                status, settings and results for every subject
- GET   /evaluations/{id}/analysis/runs/{run_id}/subjects/{sid}/evidence   the anonymised answers behind a subject
- GET   /evaluations/{id}/analysis/runs/{run_id}/findings       (optional ?subject_id=)
- POST  /evaluations/{id}/analysis/runs/{run_id}/findings       add a finding by hand
- PATCH /evaluations/{id}/analysis/runs/{run_id}/findings/{fid} accept, reject or edit
- GET   /evaluations/{id}/analysis/runs/{run_id}/conclusions
- PUT   /evaluations/{id}/analysis/runs/{run_id}/conclusions    one subject's (or the overall) conclusion
- GET   /evaluations/{id}/analysis/runs/{run_id}/completion     what still blocks "mark complete"
- POST  /evaluations/{id}/analysis/runs/{run_id}/complete       mark the analysis complete
- GET   /evaluations/{id}/analysis/compare?old=&new=            what changed between two runs
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.assembly import consultant_name
from app.db.models import AnalysisRun, Evaluation, Finding
from app.db.session import get_db
from app.services import analysis as an
from app.services import analysis_ai
from app.services import participant_portal as form

router = APIRouter()


def _evaluation(db: Session, evaluation_id: str) -> Evaluation:
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    if not form.uses_assembled_sets(db, ev.id):
        raise HTTPException(status_code=409, detail=(
            "This evaluation uses the older questionnaire. Its results are on the Responses and Report pages."))
    return ev


def _run(db: Session, ev: Evaluation, run_id: str) -> AnalysisRun:
    try:
        run = db.get(AnalysisRun, run_id)
    except Exception:  # not a UUID
        run = None
    if run is None or run.evaluation_id != ev.id:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
    return run


def _act(db: Session, fn, *args, **kwargs):
    try:
        out = fn(*args, **kwargs)
    except an.AnalysisError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return out


class RunIn(BaseModel):
    min_raters: Optional[int] = None
    include_unsubmitted: bool = False
    ai: bool = False


class FindingIn(BaseModel):
    subject_id: Optional[str] = None  # None: the whole evaluation
    kind: str
    statement: str = Field(min_length=1, max_length=4000)
    support: str
    theme_code: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    clause_ids: List[str] = Field(default_factory=list)


class FindingPatch(BaseModel):
    status: Optional[str] = None  # accepted | rejected | draft
    statement: Optional[str] = Field(default=None, max_length=4000)
    support: Optional[str] = None
    kind: Optional[str] = None


class ConclusionIn(BaseModel):
    subject_id: Optional[str] = None  # None: the overall conclusion
    text: Optional[str] = Field(default=None, max_length=8000)
    status: Optional[str] = None
    no_findings: Optional[bool] = None


@router.post("/evaluations/{evaluation_id}/analysis/runs", status_code=202)
def start_run(evaluation_id: str, background: BackgroundTasks, payload: Optional[RunIn] = None,
              db: Session = Depends(get_db), by: str = Depends(consultant_name)) -> Dict[str, Any]:
    """Start a run in the background; poll it for its status."""
    ev = _evaluation(db, evaluation_id)
    p = payload or RunIn()
    run = _act(db, an.start_run, db, ev, by, min_raters=p.min_raters, include_unsubmitted=p.include_unsubmitted,
               ai=p.ai and analysis_ai.enabled())
    background.add_task(an.execute_run, run.id)
    return an.run_dict(run)


@router.get("/evaluations/{evaluation_id}/analysis/runs")
def list_runs(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    runs = db.execute(select(AnalysisRun).where(AnalysisRun.evaluation_id == ev.id)
                      .order_by(AnalysisRun.created_at.desc())).scalars().all()
    return {"runs": [an.run_dict(r) for r in runs], "ai_available": analysis_ai.enabled()}


@router.get("/evaluations/{evaluation_id}/analysis/runs/{run_id}")
def get_run(evaluation_id: str, run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    out = an.run_dict(run)
    if run.status == "done":
        fs = an.findings(db, run)
        counts: Dict[str, Dict[str, int]] = {}
        for f in fs:
            key = str(f.evaluation_subject_id) if f.evaluation_subject_id else "overall"
            c = counts.setdefault(key, {"draft": 0, "accepted": 0, "rejected": 0})
            c["accepted" if f.status in an.ACCEPTED else f.status] += 1
        out.update(results=run.results, finding_counts=counts, blockers=an.completion_blockers(db, run))
    return out


@router.get("/evaluations/{evaluation_id}/analysis/runs/{run_id}/subjects/{subject_id}/evidence")
def subject_evidence(evaluation_id: str, run_id: str, subject_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    res = (run.results or {}).get("subjects", {}).get(subject_id)
    if res is None:
        raise HTTPException(status_code=404, detail="That subject isn't part of this analysis.")
    rows = an.subject_evidence(db, run, subject_id)
    # Nothing from suppressed results or hidden comments: the same protection as the results
    from app.services.analysis_ai import _allowed_evidence
    allowed = _allowed_evidence(res, rows)
    return {"subject_id": subject_id, "name": res["name"], "evidence": [an.evidence_dict(e, run) for e in allowed],
            "withheld": len(rows) - len(allowed)}


@router.get("/evaluations/{evaluation_id}/analysis/runs/{run_id}/findings")
def list_findings(evaluation_id: str, run_id: str, subject_id: Optional[str] = None,
                  db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    return {"findings": [an.finding_dict(db, f) for f in an.findings(db, run, subject_id)]}


@router.post("/evaluations/{evaluation_id}/analysis/runs/{run_id}/findings", status_code=201)
def add_finding(evaluation_id: str, run_id: str, payload: FindingIn, db: Session = Depends(get_db),
                by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    f = _act(db, an.add_finding, db, run, by, subject_id=payload.subject_id, kind=payload.kind,
             statement=payload.statement, support=payload.support, theme_code=payload.theme_code,
             evidence_ids=payload.evidence_ids, clause_ids=payload.clause_ids)
    return an.finding_dict(db, f)


@router.patch("/evaluations/{evaluation_id}/analysis/runs/{run_id}/findings/{finding_id}")
def update_finding(evaluation_id: str, run_id: str, finding_id: str, payload: FindingPatch,
                   db: Session = Depends(get_db), by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    try:
        f = db.get(Finding, finding_id)
    except Exception:
        f = None
    if f is None or f.run_id != run.id:
        raise HTTPException(status_code=404, detail="Finding not found.")
    f = _act(db, an.update_finding, db, run, f, by, status=payload.status, statement=payload.statement,
             support=payload.support, kind=payload.kind)
    return an.finding_dict(db, f)


@router.get("/evaluations/{evaluation_id}/analysis/runs/{run_id}/conclusions")
def list_conclusions(evaluation_id: str, run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    return {"conclusions": [an.conclusion_dict(c) for c in an.conclusions(db, run)]}


@router.put("/evaluations/{evaluation_id}/analysis/runs/{run_id}/conclusions")
def set_conclusion(evaluation_id: str, run_id: str, payload: ConclusionIn, db: Session = Depends(get_db),
                   by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    c = _act(db, an.set_conclusion, db, run, by, subject_id=payload.subject_id, text=payload.text,
             status=payload.status, no_findings=payload.no_findings)
    return an.conclusion_dict(c)


@router.get("/evaluations/{evaluation_id}/analysis/runs/{run_id}/completion")
def completion(evaluation_id: str, run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    return {"blockers": an.completion_blockers(db, run), "completed_at": an._iso(run.completed_at)}


@router.post("/evaluations/{evaluation_id}/analysis/runs/{run_id}/complete")
def mark_complete(evaluation_id: str, run_id: str, db: Session = Depends(get_db),
                  by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    run = _run(db, ev, run_id)
    return an.run_dict(_act(db, an.mark_complete, db, run, by))


@router.get("/evaluations/{evaluation_id}/analysis/compare")
def compare(evaluation_id: str, old: str, new: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    a, b = _run(db, ev, old), _run(db, ev, new)
    if a.status != "done" or b.status != "done":
        raise HTTPException(status_code=409, detail="Both runs must have finished.")
    return an.compare(db, a, b)

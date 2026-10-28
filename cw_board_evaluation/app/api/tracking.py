"""
app.api.tracking
----------------
Consultant monitoring and chasing for evaluations that use assembled question
sets (app.services.tracking). Consultant auth, like the other consultant routes;
the consultant is named by the optional X-Consultant-Name header.

- GET  /evaluations/{id}/tracking                                    summary and per-participant status
- GET  /evaluations/{id}/tracking/participants/{pid}/events          a participant's timeline
- POST /evaluations/{id}/tracking/remind                             remind one, many or all outstanding
- POST /evaluations/{id}/tracking/participants/{pid}/resend-link
- POST /evaluations/{id}/tracking/participants/{pid}/regenerate-link
- POST /evaluations/{id}/tracking/participants/{pid}/reopen          reopen a submitted form (reason required)
- PUT  /evaluations/{id}/tracking/deadline                           change the deadline, optionally notify
- POST /evaluations/{id}/tracking/close and /reopen
- GET  /evaluations/{id}/tracking/reminder-settings                  settings, schedule preview, dry run
- PUT  /evaluations/{id}/tracking/reminder-settings
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.assembly import consultant_name
from app.db.models import Evaluation, Participant
from app.db.session import get_db
from app.services import participant_portal as form
from app.services import tracking

router = APIRouter()


def _evaluation(db: Session, evaluation_id: str) -> Evaluation:
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    if not form.uses_assembled_sets(db, ev.id):
        raise HTTPException(status_code=409, detail=(
            "This evaluation uses the older questionnaire, so there's no tracking here. "
            "See the Participants page instead."))
    return ev


def _participant(db: Session, ev: Evaluation, participant_id: str) -> Participant:
    try:
        p = db.get(Participant, participant_id)
    except Exception:  # not a UUID
        p = None
    if p is None or p.evaluation_id != ev.id:
        raise HTTPException(status_code=404, detail="Participant not found in this evaluation.")
    return p


def _act(db: Session, fn, *args, **kwargs):
    try:
        out = fn(*args, **kwargs)
    except tracking.TrackingError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return out


class RemindIn(BaseModel):
    participant_ids: Optional[List[str]] = None  # omitted: everyone outstanding
    override: bool = False  # send even if reminded in the last 24 hours
    dry_run: bool = False  # who would be emailed and who skipped, for the confirmation step


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class DeadlineIn(BaseModel):
    deadline: date
    notify: bool = False


class ReminderSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    first_after_days: Optional[int] = None
    repeat_every_days: Optional[int] = None
    final_before_deadline_days: Optional[int] = None
    max_reminders: Optional[int] = None
    skip_weekends: Optional[bool] = None


@router.get("/evaluations/{evaluation_id}/tracking")
def tracking_summary(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return tracking.summary(db, _evaluation(db, evaluation_id))


@router.get("/evaluations/{evaluation_id}/tracking/participants/{participant_id}/events")
def participant_timeline(evaluation_id: str, participant_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    p = _participant(db, ev, participant_id)
    return {"participant_id": str(p.id), "name": p.full_name or p.email, "events": tracking.timeline(db, ev, p)}


@router.post("/evaluations/{evaluation_id}/tracking/remind")
def remind(evaluation_id: str, payload: RemindIn, db: Session = Depends(get_db),
           by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    results = _act(db, tracking.remind, db, ev, by, payload.participant_ids, override=payload.override,
                   dry_run=payload.dry_run)
    return {"dry_run": payload.dry_run, "results": results}


@router.post("/evaluations/{evaluation_id}/tracking/participants/{participant_id}/resend-link")
def resend_link(evaluation_id: str, participant_id: str, db: Session = Depends(get_db),
                by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    p = _participant(db, ev, participant_id)
    return _act(db, tracking.resend_link, db, ev, p.id, by)


@router.post("/evaluations/{evaluation_id}/tracking/participants/{participant_id}/regenerate-link")
def regenerate_link(evaluation_id: str, participant_id: str, db: Session = Depends(get_db),
                    by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    p = _participant(db, ev, participant_id)
    return _act(db, tracking.regenerate_link, db, ev, p.id, by)


@router.post("/evaluations/{evaluation_id}/tracking/participants/{participant_id}/reopen")
def reopen_form(evaluation_id: str, participant_id: str, payload: ReasonIn, db: Session = Depends(get_db),
                by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    p = _participant(db, ev, participant_id)
    return _act(db, tracking.reopen_form, db, ev, p.id, payload.reason, by)


@router.put("/evaluations/{evaluation_id}/tracking/deadline")
def set_deadline(evaluation_id: str, payload: DeadlineIn, db: Session = Depends(get_db),
                 by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    return _act(db, tracking.set_deadline, db, ev, payload.deadline, by, notify=payload.notify)


@router.post("/evaluations/{evaluation_id}/tracking/close")
def close_evaluation(evaluation_id: str, db: Session = Depends(get_db), by: str = Depends(consultant_name)):
    ev = _evaluation(db, evaluation_id)
    return _act(db, tracking.close_evaluation, db, ev, by)


@router.post("/evaluations/{evaluation_id}/tracking/reopen")
def reopen_evaluation(evaluation_id: str, db: Session = Depends(get_db), by: str = Depends(consultant_name)):
    ev = _evaluation(db, evaluation_id)
    return _act(db, tracking.reopen_evaluation, db, ev, by)


@router.get("/evaluations/{evaluation_id}/tracking/reminder-settings")
def reminder_settings(evaluation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return tracking.settings_view(db, _evaluation(db, evaluation_id))


@router.put("/evaluations/{evaluation_id}/tracking/reminder-settings")
def update_reminder_settings(evaluation_id: str, payload: ReminderSettingsIn, db: Session = Depends(get_db),
                             by: str = Depends(consultant_name)) -> Dict[str, Any]:
    ev = _evaluation(db, evaluation_id)
    _act(db, tracking.update_settings, db, ev, payload.model_dump(exclude_none=True), by)
    return tracking.settings_view(db, ev)

"""
app.api.scheduler
-----------------
For a hosted scheduler that can only call URLs:

    POST /api/v1/scheduler/due-reminders[?dry_run=true]
    X-Scheduler-Secret: <REMINDER_SCHEDULER_SECRET>

Not consultant auth: the secret comes from the REMINDER_SCHEDULER_SECRET environment
variable. Without it the endpoint is switched off (503). A cron job can run
scripts/send_due_reminders.py instead; both call tracking.send_due_reminders.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import tracking

router = APIRouter()

SECRET_ENV = "REMINDER_SCHEDULER_SECRET"


def require_scheduler(x_scheduler_secret: Optional[str] = Header(default=None, alias="X-Scheduler-Secret")) -> None:
    expected = (os.getenv(SECRET_ENV) or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail=f"Scheduled reminders aren't set up: {SECRET_ENV} is not set.")
    if not secrets.compare_digest((x_scheduler_secret or "").strip().encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or wrong scheduler secret.")


@router.post("/scheduler/due-reminders", dependencies=[Depends(require_scheduler)])
def due_reminders(dry_run: bool = False, db: Session = Depends(get_db)) -> Dict[str, Any]:
    out = tracking.send_due_reminders(db, dry_run=dry_run)
    db.commit()
    return out

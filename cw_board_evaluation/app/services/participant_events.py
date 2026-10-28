"""
app.services.participant_events
-------------------------------
Recording what happens to a participant's form (ParticipantEvent): emails sent
or failed, opened, first answer, submitted, and every consultant action. The
tracking status, the timeline and reminder counting all read these.

Never put email bodies, answers or link tokens in `detail`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.models import ParticipantEvent

# Events that mean an email reached the mail server, and the one that means it didn't
EMAIL_SENT = ("invite_sent", "link_resent", "reminder_sent")
EMAIL_FAILED = "email_failed"


def record(db: Session, evaluation_id: str, event_type: str, actor: str, *, participant_id=None,
           assignment_id=None, dedupe_key: Optional[str] = None, at: Optional[datetime] = None,
           **detail: Any) -> ParticipantEvent:
    # The time comes from the app, not the database's transaction time, so several events
    # written in one request keep their order (and a reminder run can record its own "now")
    e = ParticipantEvent(
        evaluation_id=evaluation_id, participant_id=participant_id, assignment_id=assignment_id,
        event_type=event_type, actor=(actor or "system")[:255], dedupe_key=dedupe_key,
        detail={k: v for k, v in detail.items() if v is not None}, created_at=at or datetime.now(timezone.utc),
    )
    db.add(e)
    db.flush()
    return e


# smtplib reports refused recipients as "{'a@b': (550, b'5.1.1 Mailbox unavailable')}"
_SMTP_REFUSAL = re.compile(r"\((\d{3}),\s*b?['\"](.+?)['\"]\)")


def short_error(err: Optional[str]) -> str:
    """The mail server's error in readable form ("550 5.1.1 Mailbox unavailable"), never the message itself."""
    text = str(err or "Unknown error")
    m = _SMTP_REFUSAL.search(text)
    if m:
        text = f"{m.group(1)} {m.group(2)}"
    return " ".join(text.split())[:300]

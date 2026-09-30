"""
Send participant hub / assignment link emails for an evaluation.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AssessmentAssignment, Evaluation, Participant
from app.services.email_service import send_assignment_links_digest_email, send_invite_email
from app.util.portal_urls import assignment_portal_url, participant_hub_url


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def assignment_link_items_for_rows(assignments: List[AssessmentAssignment]) -> List[Dict[str, Any]]:
    """Build email digest items from assignment ORM rows."""
    out: List[Dict[str, Any]] = []
    for a in assignments:
        token = _norm(getattr(a, "access_token", None))
        if not token:
            continue
        out.append(
            {
                "portal_url": assignment_portal_url(token),
                "assignment_type": a.assignment_type,
                "committee_name": a.committee_name,
                "track_code": a.assignment_type,
            }
        )
    return out


def send_evaluation_link_notifications(
    db: Session,
    evaluation_id: str,
    *,
    only_pending: bool = False,
    participant_ids: Optional[List[UUID]] = None,
    include_hub_only: bool = True,
) -> Dict[str, Any]:
    """
    Email participants their hub link and/or assignment questionnaire links.

    - Respondents with assignment links receive the digest email.
    - With include_hub_only=True, respondents with no (matching) assignments but a hub
      token receive a registration-style email with hub link only.
    """
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise ValueError(f"Evaluation not found: {evaluation_id}")

    tenant_name = ev.tenant_name

    participants: List[Participant] = (
        db.execute(select(Participant).where(Participant.evaluation_id == evaluation_id))
        .scalars()
        .all()
    )
    if participant_ids is not None:
        wanted = {str(pid) for pid in participant_ids}
        participants = [p for p in participants if str(p.id) in wanted]

    if not participants:
        return {
            "evaluation_id": evaluation_id,
            "email_sent": 0,
            "email_failed": [],
            "skipped_no_links": [],
            "only_pending": only_pending,
        }

    q = select(AssessmentAssignment).where(AssessmentAssignment.evaluation_id == evaluation_id)
    if participant_ids is not None:
        q = q.where(AssessmentAssignment.respondent_participant_id.in_(participant_ids))
    all_assignments: List[AssessmentAssignment] = db.execute(q).scalars().all()

    by_respondent: Dict[str, List[AssessmentAssignment]] = defaultdict(list)
    for a in all_assignments:
        if only_pending and str(a.status or "").lower() == "responded":
            continue
        by_respondent[str(a.respondent_participant_id)].append(a)

    email_sent = 0
    email_failed: List[Dict[str, Any]] = []
    skipped_no_links: List[Dict[str, Any]] = []

    for p in participants:
        email = _norm(p.email)
        if not email:
            email_failed.append(
                {"participant_id": str(p.id), "email": None, "error": "no email on participant"}
            )
            continue

        rid = str(p.id)
        group_rows = by_respondent.get(rid) or []
        link_items = assignment_link_items_for_rows(group_rows)
        hub = participant_hub_url((p.access_token or "").strip())

        if link_items:
            ok, err = send_assignment_links_digest_email(
                to_email=email,
                full_name=p.full_name,
                evaluation_id=evaluation_id,
                tenant_name=tenant_name,
                links=link_items,
                hub_url=hub,
            )
            if ok:
                email_sent += 1
            else:
                email_failed.append({"participant_id": rid, "email": email, "error": err})
            continue

        if include_hub_only and hub:
            ok, err = send_invite_email(
                to_email=email,
                full_name=p.full_name,
                portal_url="",
                evaluation_id=evaluation_id,
                tenant_name=tenant_name,
                hub_url=hub,
            )
            if ok:
                email_sent += 1
            else:
                email_failed.append({"participant_id": rid, "email": email, "error": err})
            continue

        skipped_no_links.append(
            {
                "participant_id": rid,
                "email": email,
                "reason": "no_assignments" if only_pending else "no_assignments_or_hub",
            }
        )

    return {
        "evaluation_id": evaluation_id,
        "email_sent": email_sent,
        "email_failed": email_failed,
        "skipped_no_links": skipped_no_links,
        "only_pending": only_pending,
    }

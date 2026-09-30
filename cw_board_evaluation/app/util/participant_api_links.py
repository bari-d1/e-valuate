"""
Consultant API shapes for participant / assignment portal links.

Terminology (Phase 4):
- hub_token: Participant.access_token — personal task hub only
- assignment_token: AssessmentAssignment.access_token — one questionnaire task
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.util.portal_urls import assignment_portal_url, participant_hub_url

TOKEN_GLOSSARY: Dict[str, str] = {
    "hub_token": "Personal task hub token (Participant.access_token). Opens /member/hub/{token}.",
    "assignment_token": "Single questionnaire token (AssessmentAssignment.access_token). Opens /member/{token}/questions.",
    "first_assignment_portal_url": "First task questionnaire URL for this participant (null until assignments exist).",
    "portal_url": "Deprecated alias for first_assignment_portal_url — do not use for hub access.",
}


def participant_hub_token(participant: Any) -> Optional[str]:
    """Hub token stored on Participant.access_token (DB column name unchanged)."""
    t = (getattr(participant, "access_token", None) or "").strip()
    return t or None


def build_participant_links_payload(
    *,
    hub_token: Optional[str],
    assignment_portal_urls: List[str],
    portal_status: str,
) -> Dict[str, Any]:
    """
    Standard link fields for invite/list participant API items.
    """
    primary = assignment_portal_urls[0] if assignment_portal_urls else None
    hub_url = participant_hub_url(hub_token) if hub_token else None
    return {
        "hub_token": hub_token,
        "hub_url": hub_url,
        "first_assignment_portal_url": primary,
        "portal_url": primary,
        "assignment_portal_urls": assignment_portal_urls,
        "portal_status": portal_status,
        "token_glossary": TOKEN_GLOSSARY,
    }


def build_assignment_links_payload(
    *,
    assignment_token: Optional[str],
    portal_url: str,
    **extra: Any,
) -> Dict[str, Any]:
    """Standard link fields for assignment rows in consultant API."""
    tok = (assignment_token or "").strip() or None
    out: Dict[str, Any] = {
        "assignment_token": tok,
        "access_token": tok,
        "portal_url": portal_url,
        "token_glossary": {
            "assignment_token": TOKEN_GLOSSARY["assignment_token"],
            "access_token": "Deprecated alias for assignment_token.",
        },
    }
    out.update(extra)
    return out

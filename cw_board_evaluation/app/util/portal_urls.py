"""
Shared helpers for Board Member portal URLs.

- Assignment questionnaire: /api/v1/portal/{token} → AssessmentAssignment.access_token
- Personal task hub: /api/v1/portal/hub/{hub_token} → Participant.access_token
"""

from __future__ import annotations

import os


def portal_base_url() -> str:
    """
    Frontend base URL used to build member portal links.

    Environment:
      PARTICIPANT_PORTAL_BASE_URL — e.g. http://localhost:5173 or https://app.example.com
    """
    base = (os.getenv("PARTICIPANT_PORTAL_BASE_URL") or "http://localhost:5173").strip()
    return base.rstrip("/")


def assignment_portal_url(access_token: str) -> str:
    """
    Full URL to the questions page for an assignment access token.

    Matches React route: /member/:token/questions
    """
    t = (access_token or "").strip()
    if not t:
        return ""
    return f"{portal_base_url()}/member/{t}/questions"


def participant_hub_url(hub_token: str) -> str:
    """
    Full URL to the member task hub for a participant access token.

    Participant.access_token is the hub token (lists all assignments for that person).
    Matches React route: /member/hub/:hubToken
    """
    t = (hub_token or "").strip()
    if not t:
        return ""
    return f"{portal_base_url()}/member/hub/{t}"

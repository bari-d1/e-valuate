"""
Consultant API key authentication (Option A — pilot).

When CONSULTANT_API_KEY is set in the environment, protected routes require:
  X-Consultant-Key: <same value>

When CONSULTANT_API_KEY is unset, auth is disabled (local dev default).

Member portal routes (/api/v1/portal/*) never use this dependency.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, status


def consultant_auth_enabled() -> bool:
    return bool((os.getenv("CONSULTANT_API_KEY") or "").strip())


def require_consultant(
    x_consultant_key: str | None = Header(default=None, alias="X-Consultant-Key"),
) -> None:
    expected = (os.getenv("CONSULTANT_API_KEY") or "").strip()
    if not expected:
        return

    provided = (x_consultant_key or "").strip()
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing consultant API key. Set header X-Consultant-Key.",
        )

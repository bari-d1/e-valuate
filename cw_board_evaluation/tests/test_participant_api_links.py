"""Unit tests for participant/assignment link API payloads."""

from __future__ import annotations

from app.util.participant_api_links import (
    build_assignment_links_payload,
    build_participant_links_payload,
)


def test_build_participant_links_payload(monkeypatch) -> None:
    monkeypatch.setenv("PARTICIPANT_PORTAL_BASE_URL", "http://localhost:5173")
    out = build_participant_links_payload(
        hub_token="hubabc",
        assignment_portal_urls=["http://localhost:5173/member/tok1/questions"],
        portal_status="ready",
    )
    assert out["hub_token"] == "hubabc"
    assert out["hub_url"] == "http://localhost:5173/member/hub/hubabc"
    assert out["first_assignment_portal_url"].endswith("/questions")
    assert out["portal_url"] == out["first_assignment_portal_url"]
    assert "hub_token" in out["token_glossary"]


def test_build_participant_links_pending() -> None:
    out = build_participant_links_payload(
        hub_token="hubonly",
        assignment_portal_urls=[],
        portal_status="pending_assignments",
    )
    assert out["first_assignment_portal_url"] is None
    assert out["portal_url"] is None


def test_build_assignment_links_payload() -> None:
    out = build_assignment_links_payload(assignment_token="asgtok", portal_url="http://x/member/asgtok/questions")
    assert out["assignment_token"] == "asgtok"
    assert out["access_token"] == "asgtok"

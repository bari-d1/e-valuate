"""Unit tests for assignment portal URL helpers (no database)."""

import os

import pytest

from app.util.portal_urls import assignment_portal_url, participant_hub_url, portal_base_url


def test_assignment_portal_url_builds_member_questions_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTICIPANT_PORTAL_BASE_URL", "https://app.example.com")
    assert (
        assignment_portal_url("abc123token")
        == "https://app.example.com/member/abc123token/questions"
    )


def test_assignment_portal_url_strips_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTICIPANT_PORTAL_BASE_URL", "http://localhost:5173")
    assert assignment_portal_url("  tok  ") == "http://localhost:5173/member/tok/questions"


def test_assignment_portal_url_empty_token_returns_empty() -> None:
    assert assignment_portal_url("") == ""
    assert assignment_portal_url("   ") == ""


def test_portal_base_url_default_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PARTICIPANT_PORTAL_BASE_URL", raising=False)
    assert portal_base_url() == "http://localhost:5173"


def test_participant_hub_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTICIPANT_PORTAL_BASE_URL", "http://localhost:5173")
    assert participant_hub_url("myhub") == "http://localhost:5173/member/hub/myhub"

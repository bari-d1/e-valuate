"""Unit tests for participant hub URL helper (no database)."""

import pytest

from app.util.portal_urls import participant_hub_url


def test_participant_hub_url_builds_member_hub_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTICIPANT_PORTAL_BASE_URL", "https://app.example.com")
    assert participant_hub_url("hubtok123") == "https://app.example.com/member/hub/hubtok123"


def test_participant_hub_url_empty() -> None:
    assert participant_hub_url("") == ""
    assert participant_hub_url("   ") == ""

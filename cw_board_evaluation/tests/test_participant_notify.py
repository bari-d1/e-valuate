"""Unit tests for participant notify helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.participant_notify import assignment_link_items_for_rows


def test_assignment_link_items_skips_empty_token(monkeypatch) -> None:
    monkeypatch.setenv("PARTICIPANT_PORTAL_BASE_URL", "http://localhost:5173")
    rows = [
        SimpleNamespace(
            access_token="tok1",
            assignment_type="BOARD_AS_WHOLE",
            committee_name=None,
        ),
        SimpleNamespace(
            access_token="",
            assignment_type="OTHER",
            committee_name=None,
        ),
    ]
    items = assignment_link_items_for_rows(rows)
    assert len(items) == 1
    assert items[0]["portal_url"] == "http://localhost:5173/member/tok1/questions"

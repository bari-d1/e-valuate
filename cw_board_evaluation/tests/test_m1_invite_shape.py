"""
Contract tests for invite/list participant JSON shape (assignment-first portal URLs).

Uses mocked DB session — no PostgreSQL required.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api import evaluations as ev
from app.util.participant_api_links import build_participant_links_payload


def test_assignment_portal_urls_for_respondent_orders_and_filters() -> None:
    db = MagicMock()
    p_id = uuid4()
    a1 = MagicMock()
    a1.access_token = "first"
    a1.created_at = 1
    a2 = MagicMock()
    a2.access_token = "second"
    a2.created_at = 2
    a_empty = MagicMock()
    a_empty.access_token = ""
    a_empty.created_at = 3

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [a1, a2, a_empty]

    db.execute.return_value = mock_result

    urls = ev._assignment_portal_urls_for_respondent(db, "eval-1", p_id)

    assert len(urls) == 2
    assert "/member/first/questions" in urls[0]
    assert "/member/second/questions" in urls[1]
    db.execute.assert_called_once()


def test_participant_links_dict_includes_hub_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTICIPANT_PORTAL_BASE_URL", "http://localhost:5173")
    p = MagicMock()
    p.access_token = "myhubtoken"
    payload = ev._participant_links_dict(p, ["http://localhost:5173/member/a1/questions"])
    assert payload["hub_token"] == "myhubtoken"
    assert payload["hub_url"] == "http://localhost:5173/member/hub/myhubtoken"
    assert payload["first_assignment_portal_url"] == "http://localhost:5173/member/a1/questions"
    assert payload["portal_url"] == payload["first_assignment_portal_url"]

"""
Integration tests: invite send_email flag + notify-links.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.db.models import AssessmentAssignment, Evaluation, Participant

pytestmark = pytest.mark.integration


def test_invite_register_without_email(api_client, db_session) -> None:
    eval_id = "eval-invite-no-email"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Notify Test",
            sector="insurance",
            year=2025,
            instrument_template_code="DEFAULT",
            instrument_version=1,
            regulators={"items": []},
        )
    )
    db_session.flush()

    with patch("app.api.evaluations.send_invite_email") as mock_send:
        res = api_client.post(
            f"/api/v1/evaluations/{eval_id}/participants/invite",
            json={
                "participants": [{"email": "quiet@example.com", "full_name": "Quiet"}],
                "send_email": False,
            },
        )
    assert res.status_code == 201, res.text
    mock_send.assert_not_called()
    body = res.json()
    assert body["send_email"] is False
    assert body["created_items"][0]["email_skipped"] is True
    assert body["created_items"][0]["email_sent"] is False
    assert body["created_items"][0]["hub_url"]


def test_notify_links_after_assignments(api_client, db_session, track_templates_seeded) -> None:
    eval_id = "eval-notify-links"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Notify Test",
            sector="insurance",
            year=2025,
            instrument_template_code="DEFAULT",
            instrument_version=1,
            regulators={"items": []},
        )
    )
    p = Participant(
        evaluation_id=eval_id,
        email="notify@example.com",
        full_name="Notify User",
        role="INED",
        status="invited",
        access_token="hubtokennotify123",
    )
    db_session.add(p)
    db_session.flush()

    db_session.add(
        AssessmentAssignment(
            evaluation_id=eval_id,
            respondent_participant_id=p.id,
            assignment_type="BOARD_AS_WHOLE",
            instrument_template_code="DEFAULT",
            instrument_version=1,
            access_token="asgtokennotify123",
            status="invited",
        )
    )
    db_session.flush()

    with patch("app.services.participant_notify.send_assignment_links_digest_email", return_value=(True, None)):
        res = api_client.post(
            f"/api/v1/evaluations/{eval_id}/participants/notify-links",
            json={"only_pending": False, "include_hub_only": True},
        )
    assert res.status_code == 200, res.text
    assert res.json()["email_sent"] == 1

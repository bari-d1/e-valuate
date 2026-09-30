"""
API tests for committee track validation on POST .../tracks.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import pytest

from app.db.models import Evaluation, Participant

pytestmark = pytest.mark.integration


def test_enable_committee_track_without_committees_rejected(api_client, db_session, track_templates_seeded) -> None:
    eval_id = "eval-committee-invalid"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Committee Test",
            sector="insurance",
            year=2025,
            instrument_template_code="DEFAULT",
            instrument_version=1,
            regulators={"items": []},
        )
    )
    db_session.flush()

    committee_tpl = next(t for t in track_templates_seeded if t.code == "COMMITTEE_EVAL")

    res = api_client.post(
        f"/api/v1/evaluations/{eval_id}/tracks",
        json={"tracks": [{"code": committee_tpl.code, "enabled": 1, "config": {}}]},
    )
    assert res.status_code == 400, res.text
    assert "committee" in res.json()["detail"].lower()


def test_enable_committee_track_with_committees_and_generate(
    api_client,
    db_session,
    track_templates_seeded,
) -> None:
    eval_id = "eval-committee-ok"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Committee Test",
            sector="insurance",
            year=2025,
            instrument_template_code="DEFAULT",
            instrument_version=1,
            regulators={"items": []},
        )
    )
    db_session.add(
        Participant(
            evaluation_id=eval_id,
            email="director@example.com",
            full_name="Director",
            role="INED",
            status="invited",
        )
    )
    db_session.flush()

    enable = api_client.post(
        f"/api/v1/evaluations/{eval_id}/tracks",
        json={
            "tracks": [
                {
                    "code": "COMMITTEE_EVAL",
                    "enabled": 1,
                    "config": {
                        "committees": ["Audit"],
                        "committee_members": {"Audit": ["director@example.com"]},
                    },
                }
            ]
        },
    )
    assert enable.status_code == 201, enable.text

    gen = api_client.post(
        f"/api/v1/evaluations/{eval_id}/tracks/generate-assignments",
        json={"dry_run": True, "send_email_notifications": False},
    )
    assert gen.status_code == 201, gen.text
    data = gen.json()
    assert data["created"] >= 1
    assert not data.get("skipped_items")

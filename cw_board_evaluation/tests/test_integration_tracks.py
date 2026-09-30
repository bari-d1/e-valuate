"""
Integration tests: enable tracks + generate assignments.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL (see tests/conftest.py).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AssessmentAssignment, Evaluation, Participant

pytestmark = pytest.mark.integration


def test_generate_assignments_from_enabled_track(
    api_client,
    db_session,
    track_templates_seeded,
) -> None:
    eval_id = "eval-int-tracks"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Track Test",
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
            email="a@example.com",
            full_name="A",
            role="INED",
            status="invited",
        )
    )
    db_session.add(
        Participant(
            evaluation_id=eval_id,
            email="b@example.com",
            full_name="B",
            role="INED",
            status="invited",
        )
    )
    db_session.flush()

    tpl = track_templates_seeded[0]
    enable = api_client.post(
        f"/api/v1/evaluations/{eval_id}/tracks",
        json={"tracks": [{"code": tpl.code, "enabled": 1, "config": {}}]},
    )
    assert enable.status_code == 201, enable.text

    gen = api_client.post(
        f"/api/v1/evaluations/{eval_id}/tracks/generate-assignments",
        json={"dry_run": False, "send_email_notifications": False},
    )
    assert gen.status_code == 201, gen.text
    data = gen.json()
    assert data["created"] >= 2
    assert data["items"]
    assert all(item.get("portal_url") for item in data["items"])

    rows = (
        db_session.execute(select(AssessmentAssignment).where(AssessmentAssignment.evaluation_id == eval_id))
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert all(r.access_token for r in rows)

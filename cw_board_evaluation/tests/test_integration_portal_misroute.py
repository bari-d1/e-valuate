"""
Integration: hub token used on assignment portal endpoint returns 409 + redirect hints.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import pytest

from app.db.models import Evaluation, Participant

pytestmark = pytest.mark.integration


def test_hub_token_on_assignment_portal_returns_misroute(api_client, db_session) -> None:
    eval_id = "eval-hub-misroute"
    hub_token = "hubtokenmisroute99"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Misroute Test",
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
            email="misroute@example.com",
            full_name="Misroute",
            role="INED",
            status="invited",
            access_token=hub_token,
        )
    )
    db_session.flush()

    res = api_client.get(f"/api/v1/portal/{hub_token}")
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "hub_token_not_assignment"
    assert detail["hub_path"] == f"/member/hub/{hub_token}"
    assert "/member/hub/" in detail["hub_url"]

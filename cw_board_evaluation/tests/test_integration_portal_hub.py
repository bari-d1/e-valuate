"""
Integration tests: participant task hub.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import AssessmentAssignment, Evaluation, Participant, Question
from app.questionnaires.presets import get_questions_for_preset

pytestmark = pytest.mark.integration


def test_portal_hub_lists_assignments(api_client, db_session) -> None:
    eval_id = "eval-int-hub"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Hub Test",
            sector="insurance",
            year=2025,
            instrument_template_code="DEFAULT",
            instrument_version=1,
            regulators={"items": []},
        )
    )
    db_session.flush()

    for q in get_questions_for_preset("default")[:2]:
        db_session.add(
            Question(
                template_code="DEFAULT",
                version=1,
                dimension=q["dimension"],
                text=q["text"],
                answer_type=q["answer_type"],
                weight=1,
                active=1,
            )
        )
    db_session.flush()

    hub_token = f"hub{uuid.uuid4().hex[:20]}"
    p = Participant(
        evaluation_id=eval_id,
        email="hub.user@example.com",
        full_name="Hub User",
        role="INED",
        status="invited",
        access_token=hub_token,
    )
    db_session.add(p)
    db_session.flush()

    for i, atype in enumerate(["BOARD_AS_WHOLE", "DIRECTOR_SELF"]):
        db_session.add(
            AssessmentAssignment(
                evaluation_id=eval_id,
                respondent_participant_id=p.id,
                assignment_type=atype,
                instrument_template_code="DEFAULT",
                instrument_version=1,
                access_token=f"asg{uuid.uuid4().hex[:18]}{i}",
                status="invited",
            )
        )
    db_session.flush()

    res = api_client.get(f"/api/v1/portal/hub/{hub_token}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["respondent"]["email"] == "hub.user@example.com"
    assert len(body["assignments"]) == 2
    assert all(a.get("portal_url") for a in body["assignments"])
    assert "/member/hub/" in body["hub_url"]


def test_portal_hub_empty_assignments(api_client, db_session) -> None:
    eval_id = "eval-int-hub-empty"
    hub_token = f"hub{uuid.uuid4().hex[:20]}"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Hub Empty",
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
            email="empty@example.com",
            full_name="Empty",
            role="INED",
            status="invited",
            access_token=hub_token,
        )
    )
    db_session.flush()

    res = api_client.get(f"/api/v1/portal/hub/{hub_token}")
    assert res.status_code == 200, res.text
    assert res.json()["assignments"] == []

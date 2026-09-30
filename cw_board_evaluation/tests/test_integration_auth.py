"""
Integration tests: consultant API key auth.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select

from app.db.models import AssessmentAssignment, Evaluation, Participant, Question
from app.questionnaires.presets import get_questions_for_preset

pytestmark = pytest.mark.integration


@pytest.fixture
def auth_key(monkeypatch):
    key = "test-consultant-key-integration"
    monkeypatch.setenv("CONSULTANT_API_KEY", key)
    return key


def test_consultant_routes_require_api_key(api_client, auth_key) -> None:
    res = api_client.post(
        "/api/v1/evaluations",
        json={
            "evaluation_id": "eval-auth-test",
            "tenant_name": "Auth Test",
            "sector": "insurance",
            "year": 2025,
            "regulators": [],
        },
    )
    assert res.status_code == 401

    res2 = api_client.post(
        "/api/v1/evaluations",
        headers={"X-Consultant-Key": auth_key},
        json={
            "evaluation_id": "eval-auth-test-ok",
            "tenant_name": "Auth Test",
            "sector": "insurance",
            "year": 2025,
            "regulators": [],
        },
    )
    assert res2.status_code == 201, res2.text


def test_portal_works_without_consultant_key(api_client, db_session, auth_key) -> None:
    eval_id = "eval-portal-auth"
    db_session.add(
        Evaluation(
            id=eval_id,
            tenant_name="Portal Auth",
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
    p = Participant(
        evaluation_id=eval_id,
        email="portal@auth.test",
        full_name="P",
        role="INED",
        status="invited",
    )
    db_session.add(p)
    db_session.flush()
    token = f"auth{uuid.uuid4().hex[:20]}"
    db_session.add(
        AssessmentAssignment(
            evaluation_id=eval_id,
            respondent_participant_id=p.id,
            assignment_type="BOARD_AS_WHOLE",
            instrument_template_code="DEFAULT",
            instrument_version=1,
            access_token=token,
            status="invited",
        )
    )
    db_session.flush()

    res = api_client.get(f"/api/v1/portal/{token}")
    assert res.status_code == 200, res.text

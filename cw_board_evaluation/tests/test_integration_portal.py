"""
Integration tests: assignment portal load + submit.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL (see tests/conftest.py).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.models import AssessmentAssignment, Evaluation, Participant, Question
from app.questionnaires.presets import get_questions_for_preset

pytestmark = pytest.mark.integration


def _seed_minimal_evaluation(db_session, eval_id: str = "eval-int-portal") -> tuple:
    ev = Evaluation(
        id=eval_id,
        tenant_name="Integration Test Plc",
        sector="insurance",
        year=2025,
        instrument_template_code="DEFAULT",
        instrument_version=1,
        regulators={"items": []},
    )
    db_session.add(ev)
    db_session.flush()

    for q in get_questions_for_preset("default")[:3]:
        db_session.add(
            Question(
                template_code="DEFAULT",
                version=1,
                dimension=q["dimension"],
                text=q["text"],
                answer_type=q["answer_type"],
                weight=int(q.get("weight", 1)),
                active=1,
            )
        )
    db_session.flush()

    p = Participant(
        evaluation_id=eval_id,
        email="portal.test@example.com",
        full_name="Portal Tester",
        role="INED",
        status="invited",
    )
    db_session.add(p)
    db_session.flush()

    token = f"tok{uuid.uuid4().hex[:24]}"
    assignment = AssessmentAssignment(
        evaluation_id=eval_id,
        respondent_participant_id=p.id,
        subject_participant_id=None,
        assignment_type="BOARD_AS_WHOLE",
        instrument_template_code="DEFAULT",
        instrument_version=1,
        access_token=token,
        status="invited",
    )
    db_session.add(assignment)
    db_session.flush()

    questions = (
        db_session.execute(
            select(Question).where(Question.template_code == "DEFAULT", Question.version == 1)
        )
        .scalars()
        .all()
    )
    return ev, p, assignment, questions


def test_portal_load_and_finalize_responses(api_client, db_session) -> None:
    _ev, _p, assignment, questions = _seed_minimal_evaluation(db_session)
    token = assignment.access_token
    assert token

    load = api_client.get(f"/api/v1/portal/{token}")
    assert load.status_code == 200, load.text
    body = load.json()
    assert body["assignment"]["assignment_id"] == str(assignment.id)
    assert len(body["questions"]) >= 1

    rating_q = next((q for q in questions if q.answer_type == "rating"), questions[0])
    answers = [{"question_id": str(rating_q.id), "score": 4, "comment": None}]

    save = api_client.post(
        f"/api/v1/portal/{token}/responses?finalize=false",
        json={"answers": answers},
    )
    assert save.status_code == 200, save.text
    assert save.json()["created"] >= 1

    got = api_client.get(f"/api/v1/portal/{token}/responses")
    assert got.status_code == 200
    assert got.json()["count"] >= 1

    fin = api_client.post(
        f"/api/v1/portal/{token}/responses?finalize=true",
        json={"answers": answers},
    )
    assert fin.status_code == 200, fin.text
    assert fin.json()["finalized"] is True
    assert fin.json()["assignment_status"] == "responded"

    db_session.refresh(assignment)
    assert assignment.status == "responded"

    dup = api_client.post(
        f"/api/v1/portal/{token}/responses?finalize=true",
        json={"answers": answers},
    )
    assert dup.status_code == 409

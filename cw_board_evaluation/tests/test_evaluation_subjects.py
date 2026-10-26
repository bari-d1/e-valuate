"""
Tests for sync_evaluation_subjects.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import importlib.util
import uuid
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import (
    AssessmentAssignment,
    AssessmentTrackTemplate,
    Evaluation,
    EvaluationSubject,
    EvaluationTrack,
    Participant,
)
from app.services.evaluation_subjects import sync_evaluation_subjects

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]


def _load_demo_seed():
    spec = importlib.util.spec_from_file_location("seed_demo_environment", ROOT / "scripts" / "seed_demo_environment.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _add_eval(db, eval_id: str) -> Evaluation:
    ev = Evaluation(
        id=eval_id, tenant_name="Subjects Test", sector="insurance", year=2025,
        instrument_template_code="DEFAULT", instrument_version=1, regulators={"items": []},
    )
    db.add(ev)
    db.flush()
    return ev


def _add_person(db, eval_id: str, n: int, role) -> Participant:
    p = Participant(evaluation_id=eval_id, email=f"person{n}@example.com", full_name=f"Person {n}", role=role, status="invited")
    db.add(p)
    db.flush()
    return p


def _types(result) -> Counter:
    return Counter(s["subject_type_code"] for s in result["created"])


def test_demo_evaluation_subjects(db_session, taxonomy_seeded) -> None:
    demo = _load_demo_seed()
    demo.seed_evaluation(db_session, "eval-002", demo.PRESETS["eval-002"])

    result = sync_evaluation_subjects(db_session, "eval-002")

    # Demo roles: Chair x2, INED x4, ED x4, Company Secretary x2 (12 participants)
    assert _types(result) == Counter({"BOARD": 1, "INED": 4, "ED": 4})
    assert result["existing"] == []
    skipped_roles = Counter(s["role"] for s in result["skipped"])
    assert skipped_roles == Counter({"Chair": 2, "Company Secretary": 2})
    assert all("Ambiguous" in s["reason"] for s in result["skipped"])
    assert not db_session.execute(
        select(EvaluationSubject).where(EvaluationSubject.subject_type_code.in_(["CHAIR", "COMPANY_SECRETARY"]))
    ).scalars().all()


def test_sync_is_idempotent(db_session, taxonomy_seeded) -> None:
    demo = _load_demo_seed()
    demo.seed_evaluation(db_session, "eval-002", demo.PRESETS["eval-002"])

    first = sync_evaluation_subjects(db_session, "eval-002")
    second = sync_evaluation_subjects(db_session, "eval-002")

    assert second["created"] == []
    assert len(second["existing"]) == len(first["created"]) == 9
    assert len(second["skipped"]) == len(first["skipped"])
    count = db_session.execute(
        select(EvaluationSubject).where(EvaluationSubject.evaluation_id == "eval-002")
    ).scalars().all()
    assert len(count) == 9


def test_roles_unknown_empty_and_single(db_session, taxonomy_seeded) -> None:
    eval_id = "eval-subjects-roles"
    _add_eval(db_session, eval_id)
    chair = _add_person(db_session, eval_id, 1, "Chair")
    ned = _add_person(db_session, eval_id, 2, "NED")
    _add_person(db_session, eval_id, 3, "Chairman")  # unknown: not guessed as CHAIR
    _add_person(db_session, eval_id, 4, None)
    _add_person(db_session, eval_id, 5, "  ")

    result = sync_evaluation_subjects(db_session, eval_id)

    assert _types(result) == Counter({"BOARD": 1, "CHAIR": 1, "NED": 1})
    by_type = {s["subject_type_code"]: s for s in result["created"]}
    assert by_type["CHAIR"]["participant_id"] == str(chair.id)
    assert by_type["NED"]["participant_id"] == str(ned.id)
    assert by_type["CHAIR"]["label"] == "Board chairman: Person 1"

    reasons = {s["email"]: s["reason"] for s in result["skipped"]}
    assert reasons["person3@example.com"].startswith("Unknown role")
    assert reasons["person4@example.com"] == "No role set."
    assert reasons["person5@example.com"] == "No role set."


def test_committees_from_enabled_track_config(db_session, taxonomy_seeded, track_templates_seeded) -> None:
    eval_id = "eval-subjects-committees"
    _add_eval(db_session, eval_id)
    member = _add_person(db_session, eval_id, 1, "INED")
    committee_tpl = next(t for t in track_templates_seeded if t.code == "COMMITTEE_EVAL")
    db_session.add(EvaluationTrack(
        evaluation_id=eval_id, track_template_id=committee_tpl.id, enabled=1,
        config={"committees": ["Audit", "Risk", "audit"]},  # duplicate (case) collapses
    ))
    # A committee that exists only on an old assignment is reported, not created
    db_session.add(AssessmentAssignment(
        evaluation_id=eval_id, respondent_participant_id=member.id, assignment_type="COMMITTEE_EVAL",
        committee_name="Legacy Committee", access_token=uuid.uuid4().hex,
    ))
    db_session.flush()

    result = sync_evaluation_subjects(db_session, eval_id)

    committees = sorted(s["committee_name"] for s in result["created"] if s["subject_type_code"] == "COMMITTEE")
    assert committees == ["Audit", "Risk"]
    assert any(s.get("committee_name") == "Legacy Committee" for s in result["skipped"])


def test_disabled_committee_track_is_ignored(db_session, taxonomy_seeded, track_templates_seeded) -> None:
    eval_id = "eval-subjects-disabled"
    _add_eval(db_session, eval_id)
    committee_tpl = next(t for t in track_templates_seeded if t.code == "COMMITTEE_EVAL")
    db_session.add(EvaluationTrack(
        evaluation_id=eval_id, track_template_id=committee_tpl.id, enabled=0, config={"committees": ["Audit"]},
    ))
    db_session.flush()

    result = sync_evaluation_subjects(db_session, eval_id)
    assert _types(result) == Counter({"BOARD": 1})


def test_unknown_evaluation(db_session, taxonomy_seeded) -> None:
    from app.services.evaluation_subjects import EvaluationNotFound

    with pytest.raises(EvaluationNotFound):
        sync_evaluation_subjects(db_session, "no-such-eval")

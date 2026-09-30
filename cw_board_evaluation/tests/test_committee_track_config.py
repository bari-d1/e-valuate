"""Unit tests for committee track config validation."""

from __future__ import annotations

import pytest

from app.db.models import AssessmentTrackTemplate
from app.services.committee_track_config import (
    is_committee_track_template,
    normalize_committee_config,
    validate_committee_config,
)


def _tpl(*, code: str = "BOARD_AS_WHOLE", subject_mode: str = "BOARD") -> AssessmentTrackTemplate:
    return AssessmentTrackTemplate(
        code=code,
        name=code,
        description="",
        assignment_type=code,
        subject_mode=subject_mode,
        subject_role=None,
        respondent_rule={"mode": "ALL"},
        default_template_code="DEFAULT",
        default_version=1,
        active=1,
    )


def test_is_committee_track_template_by_code_and_mode() -> None:
    assert is_committee_track_template(_tpl(code="COMMITTEE_EVAL", subject_mode="COMMITTEE")) is True
    assert is_committee_track_template(_tpl(code="OTHER", subject_mode="COMMITTEE")) is True
    assert is_committee_track_template(_tpl(code="BOARD_AS_WHOLE", subject_mode="BOARD")) is False


def test_normalize_committee_config_dedupes() -> None:
    cfg = normalize_committee_config(
        {
            "committees": ["Audit", "audit", " Risk "],
            "committee_members": {
                "Audit": ["A@Example.com", "a@example.com", "b@example.com"],
            },
        }
    )
    assert cfg["committees"] == ["Audit", "Risk"]
    assert cfg["committee_members"]["Audit"] == ["a@example.com", "b@example.com"]


def test_validate_committee_config_requires_committees_when_enabled() -> None:
    with pytest.raises(ValueError, match="at least one committee"):
        validate_committee_config(
            {"committees": []},
            enabled=True,
            known_participant_emails={"a@example.com"},
        )


def test_validate_committee_config_allows_empty_when_disabled() -> None:
    validate_committee_config(
        {"committees": []},
        enabled=False,
        known_participant_emails=set(),
    )


def test_validate_committee_config_unknown_email() -> None:
    with pytest.raises(ValueError, match="Unknown participant"):
        validate_committee_config(
            {
                "committees": ["Audit"],
                "committee_members": {"Audit": ["unknown@example.com"]},
            },
            enabled=True,
            known_participant_emails={"known@example.com"},
        )

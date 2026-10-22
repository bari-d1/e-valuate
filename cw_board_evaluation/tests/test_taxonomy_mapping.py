"""
Unit tests for app.domain.taxonomy (no database).
"""

from __future__ import annotations

import pytest

from app.domain.taxonomy import (
    DIMENSION_TO_THEME,
    EVIDENCE_SOURCE_CODES,
    LEGACY_ASSIGNMENT_TYPES,
    SUBJECT_TYPE_CODES,
    THEME_CODES,
    map_assignment_type,
    subject_type_for_role,
)
from app.questionnaires.presets import get_questions_for_preset

FIXED = {
    "BOARD_AS_WHOLE": "BOARD",
    "CHAIR_EVAL": "CHAIR",
    "CEO_SELF": "MD_CEO",
    "CEO_EVAL": "MD_CEO",
    "ED_SELF": "ED",
    "ED_EVAL": "ED",
    "COMMITTEE_EVAL": "COMMITTEE",
    "GOV_AUDIT": "BOARD",
}


def test_vocabulary_sizes() -> None:
    assert len(SUBJECT_TYPE_CODES) == 8
    assert len(THEME_CODES) == 12
    assert len(EVIDENCE_SOURCE_CODES) == 3


def test_all_ten_legacy_assignment_types_are_covered() -> None:
    assert set(LEGACY_ASSIGNMENT_TYPES) == set(FIXED) | {"DIRECTOR_SELF", "DIRECTOR_PEER"}
    assert len(LEGACY_ASSIGNMENT_TYPES) == 10


@pytest.mark.parametrize("assignment_type,expected", sorted(FIXED.items()))
def test_fixed_assignment_type_mapping(assignment_type: str, expected: str) -> None:
    m = map_assignment_type(assignment_type)
    assert m.subject_type_code == expected
    assert m.subject_type_code in SUBJECT_TYPE_CODES


def test_gov_audit_is_board_with_compliance_theme_and_provisional() -> None:
    m = map_assignment_type("GOV_AUDIT")
    assert (m.subject_type_code, m.theme_code, m.provisional) == ("BOARD", "COMPLIANCE_ETHICS", True)
    assert not map_assignment_type("BOARD_AS_WHOLE").provisional


@pytest.mark.parametrize("assignment_type", ["DIRECTOR_SELF", "DIRECTOR_PEER"])
@pytest.mark.parametrize("role,expected", [("NED", "NED"), ("INED", "INED"), ("ED", "ED"), (" ined ", "INED")])
def test_director_types_resolve_from_subject_role(assignment_type: str, role: str, expected: str) -> None:
    assert map_assignment_type(assignment_type, role).subject_type_code == expected


@pytest.mark.parametrize("assignment_type", ["DIRECTOR_SELF", "DIRECTOR_PEER"])
@pytest.mark.parametrize("role", [None, "", "Chair", "Company Secretary", "Chairman"])
def test_director_types_unresolved_for_non_director_roles(assignment_type: str, role) -> None:
    m = map_assignment_type(assignment_type, role)
    assert m.subject_type_code is None
    assert m.reason


def test_unknown_assignment_type_is_unresolved() -> None:
    m = map_assignment_type("SOMETHING_ELSE")
    assert m.subject_type_code is None and m.reason


@pytest.mark.parametrize(
    "role,expected",
    [
        ("Chair", "CHAIR"),
        ("chair", "CHAIR"),
        ("INED", "INED"),
        ("ED", "ED"),
        ("Company Secretary", "COMPANY_SECRETARY"),
        ("NED", "NED"),
        ("MD_CEO", "MD_CEO"),
        ("Chairman", None),
        ("CEO", None),
        ("", None),
        (None, None),
    ],
)
def test_role_mapping_only_known_values(role, expected) -> None:
    assert subject_type_for_role(role) == expected


def test_every_preset_dimension_maps_to_a_known_theme() -> None:
    dims = {q["dimension"] for q in get_questions_for_preset("expanded")}
    assert dims <= set(DIMENSION_TO_THEME)
    assert set(DIMENSION_TO_THEME.values()) <= set(THEME_CODES)

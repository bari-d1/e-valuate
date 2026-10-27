"""
Rule engine (app.domain.question_rules): every condition, nesting, missing
data, validation errors and reasons. Pure: no database.
"""

from __future__ import annotations

import pytest

from app.domain.question_rules import (
    CONDITIONS,
    RuleError,
    describe_rule,
    ensure_valid_rule,
    evaluate,
    lookup_fact,
    validate_rule,
)


def _ctx(**over):
    ctx = {
        "respondent": {"participant_id": "p6", "label": "P006", "role": "ined",
                       "committees": [{"committee_id": "c1", "role": "chair"}, {"committee_id": "c2", "role": "member"}],
                       "facts": {"holds_company_shares": {"answer": "no"}, "tenure_years": 6.5}},
        "subject": {"kind": "person", "type": "INED", "participant_id": "p6", "label": "P006",
                    "facts": {"holds_company_shares": {"answer": "no"}, "provides_advisory_services": {"answer": "unknown"},
                              "tenure_years": 6.5}},
        "org": {"sector": "insurance", "codes": ["NCCG_2018", "NAICOM_2021"],
                "facts": {"board_size": 6, "board_composition": {"women": 1, "men": 5}}},
        "evaluation": {"scope": ["BOARD", "CHAIR", "INED", "COMMITTEE"], "review_year": 2025},
    }
    for k, v in over.items():
        ctx[k] = {**ctx[k], **v} if isinstance(v, dict) else v
    return ctx


COMMITTEE = {"kind": "committee", "type": "COMMITTEE", "committee_id": "c1", "committee_type": "audit",
             "committee_name": "Statutory Audit Committee", "label": "Statutory Audit Committee",
             "facts": {"committee_member_count": 3}}


# ----------------------------
# Each condition
# ----------------------------

@pytest.mark.parametrize("rule, ctx_over, expected", [
    ({"respondent.role": ["ined"]}, {}, True),
    ({"respondent.role": ["chair", "ned"]}, {}, False),
    ({"respondent.role": ["ined"]}, {"respondent": {"role": None}}, None),
    ({"respondent.is_subject": True}, {}, True),
    ({"respondent.is_subject": True}, {"subject": {"participant_id": "p4", "label": "P004"}}, False),
    ({"respondent.is_not_subject": True}, {"subject": {"participant_id": "p4", "label": "P004"}}, True),
    ({"respondent.is_not_subject": True}, {}, False),
    ({"respondent.is_member_of_subject_committee": True}, {"subject": COMMITTEE}, True),
    ({"respondent.is_member_of_subject_committee": True}, {"subject": {**COMMITTEE, "committee_id": "c9"}}, False),
    ({"respondent.is_member_of_subject_committee": True}, {}, False),
    ({"respondent.chairs_subject_committee": True}, {"subject": COMMITTEE}, True),
    ({"respondent.chairs_subject_committee": True}, {"subject": {**COMMITTEE, "committee_id": "c2"}}, False),
    ({"subject.type": ["INED", "NED"]}, {}, True),
    ({"subject.type": ["BOARD"]}, {}, False),
    ({"subject.committee_type": ["audit"]}, {"subject": COMMITTEE}, True),
    ({"subject.committee_type": ["finance"]}, {"subject": COMMITTEE}, False),
    ({"subject.committee_type": ["audit"]}, {}, False),
    ({"subject.committee_type": ["audit"]}, {"subject": {**COMMITTEE, "committee_type": None}}, None),
    ({"subject.committee_name_contains": ["statutory"]}, {"subject": COMMITTEE}, True),
    ({"subject.committee_name_contains": ["finance"]}, {"subject": COMMITTEE}, False),
    ({"org.sector": ["insurance"]}, {}, True),
    ({"org.sector": ["banking"]}, {}, False),
    ({"org.sector": ["insurance"]}, {"org": {"sector": None}}, None),
    ({"org.has_code": "NAICOM_2021"}, {}, True),
    ({"org.has_code": "CBN_BANKS_2023"}, {}, False),
    ({"org.has_code": "NAICOM_2021"}, {"org": {"codes": []}}, None),
    ({"evaluation.scope_includes": "INED"}, {}, True),
    ({"evaluation.scope_includes": "ED"}, {}, False),
    ({"fact.known": "holds_company_shares"}, {}, True),
    ({"fact.known": "provides_advisory_services"}, {}, False),
    ({"fact.unknown": "provides_advisory_services"}, {}, True),
    ({"fact.unknown": "holds_company_shares"}, {}, False),
    ({"fact.known": "board_composition.women"}, {}, True),
    ({"fact.known": "committee_member_count"}, {"subject": COMMITTEE}, True),
    ({"fact.at_most": {"key": "board_composition.women", "value": 1}}, {}, True),
    ({"fact.at_least": {"key": "board_composition.women", "value": 2}}, {}, False),
    ({"fact.at_least": {"key": "board_size", "value": 5}}, {}, True),
    ({"fact.at_most": {"key": "board_composition.executive_directors", "value": 2}}, {}, None),
])
def test_each_condition(rule, ctx_over, expected) -> None:
    r = evaluate(rule, _ctx(**ctx_over))
    assert r.value is expected
    assert r.reasons, "every result explains itself"
    if expected is None:
        assert r.missing


def test_every_condition_is_covered() -> None:
    covered = {
        "respondent.role", "respondent.is_subject", "respondent.is_not_subject", "respondent.is_member_of_subject_committee",
        "respondent.chairs_subject_committee", "subject.type", "subject.committee_type", "subject.committee_name_contains",
        "org.sector", "org.has_code", "evaluation.scope_includes", "fact.known", "fact.unknown", "fact.at_least",
        "fact.at_most",
    }
    assert covered == set(CONDITIONS)


def test_person_facts_come_from_respondent_when_subject_is_not_a_person() -> None:
    ctx = _ctx(subject={"kind": "board", "type": "BOARD", "label": "The board", "facts": {}, "participant_id": None})
    assert lookup_fact(ctx, "tenure_years") == (True, 6.5)


# ----------------------------
# Nesting and three-valued logic
# ----------------------------

def test_nested_all_any_not() -> None:
    rule = {"all": [
        {"respondent.role": ["ined"]},
        {"any": [{"org.sector": ["banking"]}, {"org.has_code": "NAICOM_2021"}]},
        {"not": {"subject.type": ["BOARD"]}},
    ]}
    r = evaluate(rule, _ctx())
    assert r.value is True
    assert "respondent is an independent NED" in r.reasons
    assert "the evaluation is assessed against NAICOM 2021" in r.reasons


def test_all_reports_only_failing_reasons() -> None:
    r = evaluate({"all": [{"respondent.role": ["ined"]}, {"org.sector": ["banking"]}]}, _ctx())
    assert r.value is False
    assert r.reasons == ["the company is in the insurance sector, not banking"]


def test_false_beats_missing_in_all_and_true_beats_missing_in_any() -> None:
    ctx = _ctx(org={"sector": None})
    assert evaluate({"all": [{"org.sector": ["insurance"]}, {"subject.type": ["BOARD"]}]}, ctx).value is False
    assert evaluate({"any": [{"org.sector": ["insurance"]}, {"subject.type": ["INED"]}]}, ctx).value is True
    r = evaluate({"all": [{"org.sector": ["insurance"]}, {"subject.type": ["INED"]}]}, ctx)
    assert r.value is None and r.missing == ["company sector"]


def test_not_keeps_missing() -> None:
    r = evaluate({"not": {"respondent.role": ["chair"]}}, _ctx(respondent={"role": None}))
    assert r.value is None


def test_empty_rule_is_always_true() -> None:
    assert evaluate(None, _ctx()).value is True
    assert evaluate({}, _ctx()).value is True


def test_reasons_read_as_sentences() -> None:
    r = evaluate({"all": [{"respondent.role": ["ined"]}, {"respondent.is_subject": True}]}, _ctx())
    assert r.reasons == ["respondent is an independent NED", "the item is about themselves"]


# ----------------------------
# Validation
# ----------------------------

def test_unknown_condition_is_an_error_not_false() -> None:
    errors = validate_rule({"all": [{"respondent.role": ["chair"]}, {"respondent.rol": ["chair"]}]})
    assert len(errors) == 1
    assert errors[0].startswith("all[1]: unknown condition 'respondent.rol'")
    with pytest.raises(RuleError):
        evaluate({"respondent.rol": ["chair"]}, _ctx())


@pytest.mark.parametrize("rule, fragment", [
    ({"respondent.role": ["chairman"]}, "unknown governance roles: chairman"),
    ({"respondent.role": []}, "needs a non-empty list"),
    ({"respondent.is_subject": False}, "takes true"),
    ({"subject.type": ["BOARDS"]}, "unknown subject types: BOARDS"),
    ({"org.has_code": "NAICOM"}, "unknown governance code 'NAICOM'"),
    ({"org.sector": ["insurers"]}, "unknown sectors: insurers"),
    ({"fact.known": "shoe_size"}, "unknown fact key 'shoe_size'"),
    ({"fact.at_most": {"key": "board_size"}}, 'needs {"key"'),
    ({"all": []}, "needs a non-empty list of rules"),
    ({"respondent.role": ["chair"], "org.sector": ["insurance"]}, "exactly one key"),
    (["respondent.role"], "must be an object"),
])
def test_validation_messages(rule, fragment) -> None:
    errors = validate_rule(rule)
    assert errors and any(fragment in e for e in errors), errors


def test_validation_collects_every_error_with_paths() -> None:
    errors = validate_rule({"any": [{"bogus": 1}, {"not": {"subject.type": ["X"]}}]})
    assert [e.split(":")[0] for e in errors] == ["any[0]", "any[1].not"]
    with pytest.raises(RuleError) as exc:
        ensure_valid_rule({"any": [{"bogus": 1}, {"not": {"subject.type": ["X"]}}]})
    assert len(exc.value.errors) == 2


def test_describe_rule() -> None:
    rule = {"all": [{"respondent.role": ["md_ceo", "ed"]}, {"respondent.is_not_subject": True}]}
    assert describe_rule(rule) == ("respondent is the MD/CEO or an executive director and "
                                   "the item is about someone other than the respondent")
    assert describe_rule(None) == "always"
    assert describe_rule({"nope": 1}) == "invalid rule"

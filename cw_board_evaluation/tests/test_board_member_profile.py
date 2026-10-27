"""Unit tests for the board member profile registry, committee name matching and the email guard (no database)."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.board_member_profile import (
    GENERATION_ONLY_KEYS,
    INDEPENDENCE_KEYS,
    PARTICIPANT_ROLE_FOR,
    PROFILE_FACTS_BY_KEY,
    all_independence_unknown,
    effective_independence,
    governance_role_from_participant_role,
    split_generation_only,
    tenure_status,
    validate_profile_value,
)
from app.domain.org_profile import FactValueError
from app.services.committee_matching import _near, normalise_name
from app.services import email_service


# ----------------------------
# Registry
# ----------------------------

@pytest.mark.parametrize("role,expected", [
    ("Chair", "chair"), ("MD_CEO", "md_ceo"), ("ED", "ed"), ("NED", "ned"), ("INED", "ined"),
    ("Company Secretary", "company_secretary"), ("Chairman", None), ("", None), (None, None),
])
def test_role_mapping(role, expected) -> None:
    assert governance_role_from_participant_role(role) == expected


def test_participant_roles_map_back() -> None:
    for key, participant_role in PARTICIPANT_ROLE_FOR.items():
        assert governance_role_from_participant_role(participant_role) == key


def test_independence_defaults_to_unknown() -> None:
    assert len(INDEPENDENCE_KEYS) == 8
    assert all(PROFILE_FACTS_BY_KEY[k]["default"] == {"answer": "unknown"} for k in INDEPENDENCE_KEYS)
    eff = effective_independence({})
    assert set(eff) == set(INDEPENDENCE_KEYS) and all(v["answer"] == "unknown" for v in eff.values())
    assert all_independence_unknown({})
    assert not all_independence_unknown({"holds_company_shares": {"answer": "no"}})


def test_tristate_values() -> None:
    assert validate_profile_value("holds_company_shares", {"answer": "Yes", "detail": " 2% "}) == {"answer": "yes", "detail": "2%"}
    with pytest.raises(FactValueError):
        validate_profile_value("holds_company_shares", {"answer": "maybe"})
    with pytest.raises(FactValueError):
        validate_profile_value("governance_role", "chairman")


def test_personality_notes_is_generation_only() -> None:
    assert GENERATION_ONLY_KEYS == {"personality_notes"}
    assert PROFILE_FACTS_BY_KEY["personality_notes"]["generation_only"] is True
    split = split_generation_only([{"key": "governance_role"}, {"key": "personality_notes"}])
    assert [f["key"] for f in split["facts"]] == ["governance_role"]
    assert [f["key"] for f in split["generation_only_facts"]] == ["personality_notes"]


def test_tenure_is_computed() -> None:
    assert "tenure" not in PROFILE_FACTS_BY_KEY
    t = tenure_status("2015-06-01", as_of=date(2026, 10, 27))
    assert t["years"] == 11.4 and t["exceeds_limit"] is True and t["years_remaining"] == 0.0
    assert tenure_status(None)["years"] is None


# ----------------------------
# Committee name matching
# ----------------------------

@pytest.mark.parametrize("written", [
    "Chief (Mrs.) Ada OBI", "Mrs Ada Obi", "Dr. Ada Obi", "ada  obi", "Prof. Dr. Ada Obi", "Alhaja Ada Obi,",
])
def test_honorifics_and_punctuation_removed(written) -> None:
    assert normalise_name(written) == "ada obi"


def test_near_misses() -> None:
    assert _near("obi ada", "ada obi") == "same names in a different order"
    assert _near("ada ngozi obi", "ada obi") == "one name has extra parts"
    assert _near("adaeze obi", "ada obi") == "same surname and first initial"
    assert _near("ada obbi", "ada obi") == "similar spelling"
    assert _near("tunde bello", "ada obi") is None


# ----------------------------
# Email guard
# ----------------------------

@pytest.mark.parametrize("address,reserved", [
    ("p001@example.invalid", True), ("x@EXAMPLE.com", True), ("x@example.org", True), ("x@foo.invalid", True),
    ("x@example.com.ng", False), ("member01@demo-client.test", False), ("", False),
])
def test_reserved_addresses(address, reserved) -> None:
    assert email_service.is_reserved_address(address) is reserved


def test_reserved_addresses_are_never_sent(monkeypatch, caplog) -> None:
    monkeypatch.setenv("EMAIL_ENABLED", "true")

    def no_smtp(*a, **kw):
        raise AssertionError("SMTP must not be used for reserved addresses")

    monkeypatch.setattr(email_service.smtplib, "SMTP", no_smtp)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", no_smtp, raising=False)
    with caplog.at_level("INFO"):
        ok, err = email_service.send_invite_email("P001@example.invalid", "Member", "http://x/p", "eval-1")
        ok2, err2 = email_service.send_assignment_links_digest_email("a@example.com", None, "eval-1", None,
                                                                     [{"portal_url": "http://x/p"}])
    assert (ok, err) == (ok2, err2) == (False, email_service.RESERVED_SKIP_MESSAGE)
    assert "reserved test domain" in caplog.text and "P001" not in caplog.text

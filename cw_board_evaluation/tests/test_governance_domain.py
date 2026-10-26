"""
Unit tests for governance reference data, sector normalisation, the clause
fixtures and the tag rules (no database).
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from app.domain.governance import (
    GOVERNANCE_CODES,
    SECTOR_CODE_DEFAULTS,
    normalize_sector,
)
from app.domain.taxonomy import SUBJECT_TYPE_CODES, THEME_CODES
from app.services.governance import FIXTURE_DIR, TAG_RULES_PATH, read_tag_rules

CODES = {c["code"]: c for c in GOVERNANCE_CODES}


def _fixture(code: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{code}.json").read_text(encoding="utf-8"))


# ----------------------------
# Code metadata
# ----------------------------

def test_eight_codes_registered() -> None:
    assert set(CODES) == {
        "NCCG_2018", "NAICOM_2021", "CBN_BANKS_2023", "CBN_MFB_2018",
        "PENCOM_2025", "NCC_2025", "SME_2024", "SEC_2011",
    }
    assert GOVERNANCE_CODES[0]["code"] == "NCCG_2018"  # base code first (self-FK)


def test_sec_2011_is_historical_with_note() -> None:
    sec = CODES["SEC_2011"]
    assert sec["status"] == "historical"
    assert sec["notes"] == (
        "CBN 2023 states NCCG 2018 replaced sectoral codes; awaiting client confirmation of whether "
        "SEC 2011 still applies."
    )


def test_supplements() -> None:
    supplements = {c for c, v in CODES.items() if v["supplements_code"] == "NCCG_2018"}
    assert supplements == {"NAICOM_2021", "CBN_BANKS_2023", "PENCOM_2025", "NCC_2025"}
    assert all(v["status"] == "current" for c, v in CODES.items() if c != "SEC_2011")


# ----------------------------
# Sectors
# ----------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("insurance", ("insurance", None)),
        ("Insurance", ("insurance", None)),
        ("INSURANCE ", ("insurance", None)),
        ("Insurance sector", ("insurance", None)),
        ("Insurance & Reinsurance", ("insurance", None)),
        ("Commercial Bank", ("banking", None)),
        ("Non-Interest Bank", ("banking", None)),
        ("Microfinance Bank", ("banking", "microfinance")),
        ("MFB", ("banking", "microfinance")),
        ("Pension", ("pension", None)),
        ("Telecoms", ("telecommunications", None)),
        ("Telecommunications industry", ("telecommunications", None)),
        ("SMEs", ("sme", None)),
        ("finance", ("finance", None)),
        ("Financial Services", (None, None)),  # ambiguous: not guessed
        ("Oil & Gas", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_normalize_sector(text, expected) -> None:
    assert normalize_sector(text) == expected


def test_sector_defaults() -> None:
    by = {}
    for sector, sub, code in SECTOR_CODE_DEFAULTS:
        by.setdefault((sector, sub), set()).add(code)
    assert by == {
        ("insurance", None): {"NCCG_2018", "NAICOM_2021"},
        ("banking", None): {"NCCG_2018", "CBN_BANKS_2023"},
        ("banking", "microfinance"): {"NCCG_2018", "CBN_MFB_2018"},
        ("pension", None): {"NCCG_2018", "PENCOM_2025"},
        ("telecommunications", None): {"NCCG_2018", "NCC_2025"},
        ("sme", None): {"SME_2024"},
        ("finance", None): {"NCCG_2018"},
    }
    assert {code for _, _, code in SECTOR_CODE_DEFAULTS} <= set(CODES)


# ----------------------------
# Clause fixtures
# ----------------------------

@pytest.mark.parametrize("code", ["NCCG_2018", "NAICOM_2021"])
def test_fixture_integrity(code: str) -> None:
    fx = _fixture(code)
    assert fx["code"] == code and fx["clause_count"] == len(fx["clauses"])
    refs = [c["reference"] for c in fx["clauses"]]
    assert len(refs) == len(set(refs)), "duplicate references"
    assert all(c["parent_reference"] in set(refs) for c in fx["clauses"] if c["parent_reference"])
    orders = [c["sort_order"] for c in fx["clauses"]]
    assert orders == sorted(orders)
    # parents always come before their children
    seen = set()
    for c in fx["clauses"]:
        assert c["parent_reference"] is None or c["parent_reference"] in seen
        seen.add(c["reference"])
    assert fx["checks"]["toc_mismatches"] is not None
    assert fx["checks"]["numbering_gaps"] == []
    assert fx["checks"]["citations"]["unresolved"] == []


def test_nccg_fixture_matches_table_of_contents() -> None:
    fx = _fixture("NCCG_2018")
    levels = Counter(c["level"] for c in fx["clauses"])
    assert levels == {"part": 7, "principle": 29, "practice": 367}
    assert fx["checks"]["toc_mismatches"] == []
    by = {c["reference"]: c for c in fx["clauses"]}
    assert by["2.7"]["parent_reference"] == "2" and "separate" in by["2.7"]["text"]
    assert by["11.4"]["heading"] == "Committee responsible for Audit"
    assert by["2"]["parent_reference"] == "Part A"
    assert by["29"]["heading"] == "Definitions"


def test_naicom_fixture_sections_and_citations() -> None:
    fx = _fixture("NAICOM_2021")
    levels = Counter(c["level"] for c in fx["clauses"])
    assert levels == {"section": 13, "subsection": 8}
    by = {c["reference"]: c for c in fx["clauses"]}
    assert by["2.01"]["cites"] == "NCCG_2018:2.7"
    assert by["2.2"]["cites"] == "NCCG_2018:11.1.6"
    assert "extraction_note" in by["12.0"] and "extraction_note" in by["13.0"]  # scanned page
    nccg = {c["reference"] for c in _fixture("NCCG_2018")["clauses"]}
    assert {"2.7", "11.1.6"} <= nccg


# ----------------------------
# Tag rules
# ----------------------------

def test_tag_rules_use_known_codes() -> None:
    rules = read_tag_rules(TAG_RULES_PATH)
    assert rules
    for r in rules:
        assert r["code"] in CODES
        assert set(r["subject_types"]) <= set(SUBJECT_TYPE_CODES), r
        assert r["theme"] is None or r["theme"] in THEME_CODES, r
        assert r["subject_types"] or r["theme"], f"rule tags nothing: {r}"


def test_tag_rule_headings_exist_in_fixtures() -> None:
    def norm(s):
        import re
        return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("&", "and")).strip()

    headings = {
        code: {norm(c["heading"]) for c in _fixture(code)["clauses"] if c["heading"] and c["level"] != "part"}
        for code in ("NCCG_2018", "NAICOM_2021")
    }
    for r in read_tag_rules(TAG_RULES_PATH):
        assert norm(r["heading"]) in headings[r["code"]], r

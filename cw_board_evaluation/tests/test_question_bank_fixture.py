"""
The draft question bank fixture (reference/question_bank/draft_bank.json):
valid, loadable, traceable and free of admin fields. Pure: no database.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pytest

from app.domain.question_bank import validate_item
from app.domain.question_rules import validate_rule
from app.domain.taxonomy import EVIDENCE_SOURCE_CODES, SUBJECT_TYPE_CODES, THEME_CODES

ROOT = Path(__file__).resolve().parents[1]
BANK_DIR = ROOT / "reference" / "question_bank"
FIXTURE = BANK_DIR / "draft_bank.json"
TAGS = ("subject_types", "subject_binding", "respondent_rule", "activation_rule", "theme", "evidence_source")


@pytest.fixture(scope="module")
def bank():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def clauses():
    out = set()
    for path in (ROOT / "reference" / "governance").glob("*.json"):
        fx = json.loads(path.read_text(encoding="utf-8"))
        out.update((fx["code"], c["reference"]) for c in fx["clauses"])
    return out


def test_fixture_shape(bank) -> None:
    assert bank["format"] == "cw-question-bank"
    assert bank["format_version"] == 1
    assert len(bank["items"]) == 246


def test_codes_are_unique_and_stable(bank) -> None:
    keys = [(i["code"], i["version"]) for i in bank["items"]]
    assert len(keys) == len(set(keys))
    assert all(re.match(r"^[A-Z]+(-[A-Z]+)*-\d{2}$", i["code"]) for i in bank["items"])


def test_every_item_validates_and_is_a_draft(bank) -> None:
    for item in bank["items"]:
        validate_item(item)  # raises with the item's problems
        assert item["status"] == "draft", item["code"]


def test_every_rule_validates(bank) -> None:
    for item in bank["items"]:
        for key in ("respondent_rule", "activation_rule"):
            assert validate_rule(item[key]) == [], (item["code"], key)


def test_every_tag_code_exists(bank, clauses) -> None:
    for item in bank["items"]:
        assert item["theme_code"] in THEME_CODES, item["code"]
        assert item["evidence_source_code"] in EVIDENCE_SOURCE_CODES, item["code"]
        assert set(item["subject_types"]) <= set(SUBJECT_TYPE_CODES), item["code"]
        for ref in item["governance_refs"]:
            assert (ref["code"], ref["reference"]) in clauses, (item["code"], ref)


def test_every_tag_is_suggested_with_a_reason(bank) -> None:
    for item in bank["items"]:
        notes = item["tag_notes"]
        for tag in TAGS + (("governance_refs",) if item["governance_refs"] else ()):
            assert notes[tag]["status"] == "suggested", (item["code"], tag)
            assert notes[tag]["reason"].strip(), (item["code"], tag)


ADMIN = re.compile(r"^\s*(e-?mail|name|designation|position|date of (first )?appointment|"
                   r"committees? (you )?belongs? to)\b", re.I)


def test_no_admin_fields_left(bank) -> None:
    for item in bank["items"]:
        assert not ADMIN.match(item["text"]), item["code"]


def test_every_source_item_is_traced_once(bank) -> None:
    forms = {f["form_id"]: f for f in bank["source_forms"]}
    seen = {}
    for item in bank["items"]:
        assert item["source_refs"], item["code"]
        for ref in item["source_refs"]:
            assert ref["form"] == forms[ref["form_id"]]["name"]  # only the listed form names, never free text
            key = (ref["form_id"], ref["item"])
            assert key not in seen, f"{key} on {seen[key]} and {item['code']}"
            seen[key] = item["code"]
    for form_id, form in forms.items():
        assert sum(1 for f, _ in seen if f == form_id) == form["items_before"], form_id
    assert sum(f["items_before"] for f in forms.values()) == 405


def test_merges(bank) -> None:
    by_code = {i["code"]: i for i in bank["items"]}
    # The five NED peer forms are one template
    assert len({r["form_id"] for r in by_code["PEER-NED-01"]["source_refs"]}) == 5
    # The four committee forms share a core set
    core = [i for i in bank["items"] if i["code"].startswith("COM-CORE-")]
    assert len(core) == 21
    assert all(len(i["source_refs"]) == 4 for i in core)


def test_templated_and_known_items(bank) -> None:
    by_code = {i["code"]: i for i in bank["items"]}
    assert by_code["BOARD-EFF-01"]["placeholders"] == ["board_composition.women"]
    assert "{board_composition.women}" in by_code["BOARD-EFF-01"]["text"]
    assert not any("2022" in i["text"] for i in bank["items"]), "hard-coded years are templated"
    known = {i["code"]: i["known_from"] for i in bank["items"] if i["known_from"]}
    assert known["INED-IND-01"] == "holds_company_shares"
    assert known["INED-IND-09"] == "tenure_years"
    assert known["DIR-SELF-02"] == "expertise"


def test_csv_matches_json(bank) -> None:
    sys.path.insert(0, str(ROOT / "scripts" / "question_bank"))
    import export_csv

    with (BANK_DIR / "draft_bank.csv").open(newline="", encoding="utf-8") as fh:
        on_disk = list(csv.DictReader(fh))
    expected = [{k: str(v) for k, v in row.items()} for row in export_csv.rows(bank)]
    assert on_disk == expected, "draft_bank.csv is stale: run scripts/question_bank/export_csv.py"

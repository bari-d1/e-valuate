"""
Integration tests: loading clause fixtures, tagging, sector defaults and the
governance API.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import GovernanceClause, GovernanceCode
from app.services.governance import (
    apply_tag_rules,
    default_codes_for_sector,
    fixture_paths,
    load_clause_fixtures,
    read_fixture,
    read_tag_rules,
    seed_governance_codes,
    seed_sector_code_defaults,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def governance_seeded(db_session, taxonomy_seeded):
    seed_governance_codes(db_session)
    seed_sector_code_defaults(db_session)
    return db_session


@pytest.fixture
def library_loaded(governance_seeded):
    db = governance_seeded
    summary = load_clause_fixtures(db, [read_fixture(p) for p in fixture_paths()])
    tagging = apply_tag_rules(db, list(summary["codes"]), read_tag_rules())
    return db, summary, tagging


def _clause(db, code, ref) -> GovernanceClause:
    return db.execute(
        select(GovernanceClause).where(GovernanceClause.code == code, GovernanceClause.reference == ref)
    ).scalar_one()


def test_seed_helpers_are_idempotent(governance_seeded) -> None:
    assert seed_governance_codes(governance_seeded) == {"governance_codes": 0}
    assert seed_sector_code_defaults(governance_seeded) == {"sector_code_defaults": 0}


def test_load_fixtures(library_loaded) -> None:
    db, summary, _ = library_loaded
    assert summary["codes"]["NCCG_2018"]["created"] == 403
    assert summary["codes"]["NAICOM_2021"]["created"] == 21
    assert summary["unresolved_citations"] == []

    assert db.get(GovernanceCode, "NCCG_2018").clauses_loaded is True
    assert db.get(GovernanceCode, "NAICOM_2021").clauses_loaded is True
    assert db.get(GovernanceCode, "CBN_BANKS_2023").clauses_loaded is False

    practice = _clause(db, "NCCG_2018", "2.8.1")
    assert practice.parent_id == _clause(db, "NCCG_2018", "2.8").id
    assert _clause(db, "NAICOM_2021", "2.01").cites_clause_id == _clause(db, "NCCG_2018", "2.7").id
    assert _clause(db, "NAICOM_2021", "2.2").cites_clause_id == _clause(db, "NCCG_2018", "11.1.6").id


def test_reload_is_idempotent_and_keeps_ids(library_loaded) -> None:
    db, _, _ = library_loaded
    before = _clause(db, "NCCG_2018", "2.7").id
    again = load_clause_fixtures(db, [read_fixture(p) for p in fixture_paths()])
    assert again["codes"]["NCCG_2018"] == {"created": 0, "updated": 403, "removed": 0}
    assert _clause(db, "NCCG_2018", "2.7").id == before


def test_loader_requires_registered_code(db_session, taxonomy_seeded) -> None:
    with pytest.raises(ValueError, match="not registered"):
        load_clause_fixtures(db_session, [read_fixture(fixture_paths(["NCCG_2018"])[0])])


def test_tagging(library_loaded) -> None:
    db, _, tagging = library_loaded
    assert tagging["unmatched_rules"] == []

    def tags(code, ref):
        c = _clause(db, code, ref)
        return c.subject_type_codes, c.theme_code

    assert tags("NCCG_2018", "3.1") == (["CHAIR"], None)                       # inherited from "Chairman"
    assert tags("NCCG_2018", "7") == (["INED"], "INDEPENDENCE")
    assert tags("NCCG_2018", "11.4.2") == (["COMMITTEE"], "AUDIT_ASSURANCE")   # sub-heading overrides principle 11
    assert tags("NCCG_2018", "17.1.1") == ([], "RISK_MONITORING")
    assert tags("NCCG_2018", "Part B") == ([], None)                            # parts are never tagged
    assert tags("NCCG_2018", "29.1.1") == ([], None)                            # definitions: untagged
    assert tags("NAICOM_2021", "2.01") == (["BOARD"], "BOARD_COMPOSITION")

    untagged = {(u["code"], u["reference"]) for u in tagging["untagged"]}
    assert ("NAICOM_2021", "1.0") in untagged and ("NCCG_2018", "29") in untagged
    assert not any(code == "NCCG_2018" and ref.split(".")[0] != "29" for code, ref in untagged)


def test_default_codes_for_sector(governance_seeded) -> None:
    db = governance_seeded
    assert default_codes_for_sector(db, "Insurance") == ["NAICOM_2021", "NCCG_2018"]
    assert default_codes_for_sector(db, "INSURANCE ") == ["NAICOM_2021", "NCCG_2018"]
    assert default_codes_for_sector(db, "Microfinance Bank") == ["CBN_MFB_2018", "NCCG_2018"]
    assert default_codes_for_sector(db, "Commercial Bank") == ["CBN_BANKS_2023", "NCCG_2018"]
    assert default_codes_for_sector(db, "SMEs") == ["SME_2024"]
    assert default_codes_for_sector(db, "Oil & Gas") == []


# ----------------------------
# API
# ----------------------------

def test_api_list_and_detail(api_client, library_loaded) -> None:
    res = api_client.get("/api/v1/governance-codes")
    assert res.status_code == 200, res.text
    items = {i["code"]: i for i in res.json()["items"]}
    assert len(items) == 8
    assert items["NCCG_2018"]["clause_count"] == 403 and items["NCCG_2018"]["clauses_loaded"] is True
    assert items["SEC_2011"]["status"] == "historical"
    assert res.json()["items"][-1]["code"] == "SEC_2011"

    detail = api_client.get("/api/v1/governance-codes/NCCG_2018").json()
    assert detail["clause_counts_by_level"] == {"part": 7, "principle": 29, "practice": 367}
    assert detail["supplemented_by"] == ["CBN_BANKS_2023", "NAICOM_2021", "NCC_2025", "PENCOM_2025"]
    assert api_client.get("/api/v1/governance-codes/NOPE").status_code == 404


def test_api_clauses_hierarchy_and_filters(api_client, library_loaded) -> None:
    allc = api_client.get("/api/v1/governance-codes/NCCG_2018/clauses").json()
    assert allc["count"] == 403
    by = {c["reference"]: c for c in allc["items"]}
    assert by["2.8.1"]["parent_reference"] == "2.8"
    assert [p["reference"] for p in by["2.8.1"]["path"]] == ["Part A", "2", "2.8"]
    assert by["2.8.1"]["depth"] == 3

    chair = api_client.get("/api/v1/governance-codes/NCCG_2018/clauses", params={"subject": "chair"}).json()
    assert chair["count"] > 0 and all("CHAIR" in c["subject_type_codes"] for c in chair["items"])

    audit = api_client.get(
        "/api/v1/governance-codes/NCCG_2018/clauses", params={"subject": "COMMITTEE", "theme": "AUDIT_ASSURANCE"}
    ).json()
    assert audit["items"][0]["reference"] == "11.4"

    q = api_client.get("/api/v1/governance-codes/NAICOM_2021/clauses", params={"q": "Principle 2.7"}).json()
    assert [c["reference"] for c in q["items"]] == ["2.01"]
    assert q["items"][0]["cites"]["reference"] == "2.7" and q["items"][0]["cites"]["code"] == "NCCG_2018"

    assert api_client.get("/api/v1/governance-codes/NCCG_2018/clauses", params={"theme": "NOPE"}).status_code == 400
    assert api_client.get("/api/v1/governance-codes/NCCG_2018/clauses", params={"subject": "NOPE"}).status_code == 400
    assert api_client.get("/api/v1/governance-codes/NOPE/clauses").status_code == 404

"""
Question bank: versioning, the loader and the API.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.models import QuestionBankItem, QuestionBankItemClause
from app.services import question_bank as svc
from app.services.governance import fixture_paths, load_clause_fixtures, read_fixture

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"
API = "/api/v1/question-bank"

ITEM = {
    "code": "TEST-ITEM-01",
    "text": "The board reviews its own effectiveness each year",
    "answer_type": "rating",
    "scale": {"min": 1, "max": 5, "labels": {"1": "Poor", "5": "Excellent"}},
    "subject_types": ["BOARD"],
    "subject_binding": "none",
    "respondent_rule": {"respondent.role": ["chair", "ned"]},
    "theme_code": "BOARD_EFFECTIVENESS",
    "evidence_source_code": "PERCEPTION",
}


@pytest.fixture
def clauses(db_session, reference_seeded):
    load_clause_fixtures(db_session, [read_fixture(p) for p in fixture_paths()])
    return db_session


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


# ----------------------------
# Loader
# ----------------------------

def test_loader_is_idempotent(db_session, clauses) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = svc.load_fixture(db_session, fixture)
    assert len(first["created"]) == 288
    assert first["errors"] == [] and first["unresolved_clauses"] == []
    links = _count(db_session, QuestionBankItemClause)
    assert links > 0
    second = svc.load_fixture(db_session, fixture)
    assert second["created"] == [] and len(second["unchanged"]) == 288
    assert _count(db_session, QuestionBankItem) == 288
    assert _count(db_session, QuestionBankItemClause) == links
    item = db_session.execute(select(QuestionBankItem).where(QuestionBankItem.code == "INED-IND-01")).scalar_one()
    assert [(link.clause.code, link.clause.reference, link.status) for link in item.clause_links] == [("NCCG_2018", "7.2.1", "suggested")]


def test_loader_leaves_consultant_edits_alone(db_session, clauses) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    svc.load_fixture(db_session, fixture)
    item = db_session.execute(select(QuestionBankItem).where(QuestionBankItem.code == "BOARD-GEN-01")).scalar_one()
    svc.update_item(db_session, item, {"text": "Any other comments?"})
    svc.load_fixture(db_session, fixture)
    assert item.text == "Any other comments?"
    svc.load_fixture(db_session, fixture, update_drafts=True)
    assert item.text.startswith("Please give any comments")


def test_loader_reports_what_does_not_load(db_session, reference_seeded) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = copy.deepcopy(fixture["items"][:3])
    items[0]["respondent_rule"] = {"respondent.rol": ["chair"]}
    items[1]["theme_code"] = "NOT_A_THEME"
    items[2]["governance_refs"] = [{"code": "NCCG_2018", "reference": "99.9"}]
    summary = svc.load_fixture(db_session, {**fixture, "items": items})  # no clauses loaded in this test
    assert [e["item"] for e in summary["errors"]] == [f"{items[0]['code']} v1", f"{items[1]['code']} v1"]
    assert "unknown condition 'respondent.rol'" in summary["errors"][0]["errors"][0]
    assert any("NOT_A_THEME" in e for e in summary["errors"][1]["errors"])
    assert summary["created"] == [f"{items[2]['code']} v1"]
    assert summary["unresolved_clauses"] == [{"item": f"{items[2]['code']} v1", "code": "NCCG_2018", "reference": "99.9"}]
    with pytest.raises(ValueError):
        svc.load_fixture(db_session, {"items": []})


# ----------------------------
# Versioning
# ----------------------------

def test_editing_an_approved_item_creates_version_2(db_session, clauses) -> None:
    item = svc.create_item(db_session, ITEM)
    svc.link_clause(db_session, item, svc.find_clause(db_session, "NCCG_2018", "14"), "confirmed")
    svc.approve_item(db_session, item)
    v2, new = svc.update_item(db_session, item, {"text": "The board reviews its effectiveness annually"})
    assert new and v2.version == 2 and v2.status == "draft" and v2.id != item.id
    assert item.version == 1 and item.status == "approved"
    assert item.text == ITEM["text"], "version 1 stays as it was, for audit"
    assert [link.clause.reference for link in v2.clause_links] == ["14"]
    with pytest.raises(svc.BankConflict):
        svc.update_item(db_session, item, {"text": "Edit an old version"})
    # A draft changes in place
    same, new = svc.update_item(db_session, v2, {"text": "Draft wording"})
    assert same.id == v2.id and not new and v2.version == 2
    svc.approve_item(db_session, v2)
    assert [v.status for v in svc.versions_of(db_session, ITEM["code"])] == ["approved", "approved"]
    svc.retire_item(db_session, v2)
    with pytest.raises(svc.BankConflict):
        svc.update_item(db_session, v2, {"text": "x"})


# ----------------------------
# API
# ----------------------------

def test_api_create_edit_approve_retire(api_client, clauses) -> None:
    r = api_client.post(f"{API}/items", json=ITEM)
    assert r.status_code == 201, r.text
    v1 = r.json()["item"]
    assert v1["version"] == 1 and v1["status"] == "draft"
    assert v1["respondent_rule_text"] == "respondent is the chair or a non-executive director"

    assert api_client.post(f"{API}/items", json=ITEM).status_code == 400  # code already exists

    r = api_client.patch(f"{API}/items/{v1['id']}", json={"text": "Edited while still a draft"})
    assert r.status_code == 200 and r.json()["new_version"] is False

    assert api_client.post(f"{API}/items/{v1['id']}/approve").json()["item"]["status"] == "approved"
    r = api_client.patch(f"{API}/items/{v1['id']}", json={"text": "Edited after approval"})
    body = r.json()
    assert body["new_version"] is True and body["item"]["version"] == 2
    assert [v["status"] for v in body["versions"]] == ["approved", "draft"]
    v2 = body["item"]
    assert api_client.get(f"{API}/items/{v1['id']}").json()["item"]["text"] == "Edited while still a draft"

    r = api_client.patch(f"{API}/items/{v1['id']}", json={"text": "old"})
    assert r.status_code == 409 and "latest version (v2)" in r.json()["detail"]

    r = api_client.post(f"{API}/items/{v2['id']}/retire")
    assert r.json()["item"]["status"] == "retired"
    assert api_client.post(f"{API}/items/{v2['id']}/approve").status_code == 409


def test_api_rejects_invalid_items_with_every_error(api_client, reference_seeded) -> None:
    bad = {**ITEM, "code": "bad", "answer_type": "single_select", "respondent_rule": {"respondent.role": ["boss"]},
           "theme_code": "NOPE"}
    r = api_client.post(f"{API}/items", json=bad)
    assert r.status_code == 400
    errors = r.json()["detail"]["errors"]
    assert any(e.startswith("Code must look like") for e in errors)
    assert any("at least two options" in e for e in errors)
    assert any("unknown governance roles: boss" in e for e in errors)
    assert any("NOPE" in e for e in errors)


def test_api_list_filters(api_client, db_session, clauses) -> None:
    svc.load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    body = api_client.get(f"{API}/items").json()
    assert body["total"] == 288 and body["status_counts"]["draft"] == 288
    ined = api_client.get(f"{API}/items", params={"subject_type": "INED", "theme": "INDEPENDENCE"}).json()["items"]
    assert {i["code"] for i in ined} == {f"INED-IND-{n:02d}" for n in range(1, 10)} | {"PEER-NED-04", "DIR-SELF-03", "PEER-CORE-02", "SELF-CORE-02"}
    found = api_client.get(f"{API}/items", params={"q": "whistleblowing"}).json()["items"]
    assert "BOARD-RISK-04" in {i["code"] for i in found}
    assert api_client.get(f"{API}/items", params={"evidence_source": "ORG_FACT", "status": "approved"}).json()["total"] == 0


def test_api_clause_links(api_client, db_session, clauses) -> None:
    svc.load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    item = db_session.execute(select(QuestionBankItem).where(QuestionBankItem.code == "BOARD-RISK-04")).scalar_one()
    detail = api_client.get(f"{API}/items/{item.id}").json()["item"]
    assert [(c["code"], c["reference"], c["status"]) for c in detail["clauses"]] == [
        ("NAICOM_2021", "11.0", "suggested"), ("NCCG_2018", "19", "suggested")]
    naicom = detail["clauses"][0]["clause_id"]
    nccg = detail["clauses"][1]["clause_id"]
    r = api_client.post(f"{API}/items/{item.id}/clauses/{nccg}/confirm")
    assert [c["status"] for c in r.json()["item"]["clauses"]] == ["suggested", "confirmed"]
    r = api_client.delete(f"{API}/items/{item.id}/clauses/{naicom}")
    assert [c["reference"] for c in r.json()["item"]["clauses"]] == ["19"]
    r = api_client.post(f"{API}/items/{item.id}/clauses", json={"code": "NCCG_2018", "reference": "19.2"})
    assert r.status_code == 201
    assert ("19.2", "confirmed") in [(c["reference"], c["status"]) for c in r.json()["item"]["clauses"]]
    assert api_client.post(f"{API}/items/{item.id}/clauses", json={"code": "NCCG_2018", "reference": "99"}).status_code == 400
    assert api_client.delete(f"{API}/items/{item.id}/clauses/{naicom}").status_code == 404


def test_api_rule_validation_and_meta(api_client, reference_seeded) -> None:
    ok = api_client.post(f"{API}/rules/validate", json={"rule": {"org.has_code": "NAICOM_2021"}}).json()
    assert ok == {"valid": True, "errors": [], "description": "the evaluation uses NAICOM 2021"}
    bad = api_client.post(f"{API}/rules/validate", json={"rule": {"any": [{"org.code": "X"}]}}).json()
    assert bad["valid"] is False and bad["errors"][0].startswith("any[0]: unknown condition 'org.code'")
    meta = api_client.get(f"{API}/meta").json()
    assert "respondent.is_not_subject" in {c["name"] for c in meta["conditions"]}
    assert {"key": "tenure_years", "label": "Years on the board (from the appointment date)", "scope": "person"} in meta["fact_keys"]
    assert "NAICOM_2021" in meta["governance_codes"]
    assert api_client.get(f"{API}/items/not-a-uuid").status_code == 404

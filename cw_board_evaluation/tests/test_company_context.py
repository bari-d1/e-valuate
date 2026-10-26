"""
Profile review rules, context snapshots, governance codes per organisation,
and the organisation/evaluation API.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from app.db.models import (
    Evaluation,
    EvaluationGovernanceCode,
    Organisation,
    OrganisationFact,
    OrgCommittee,
)
from app.services import profile_review as review
from app.services.organisations import apply_evaluation_code_defaults, link_sector_defaults

pytestmark = pytest.mark.integration

ALL_SUBJECT_TYPES = ["BOARD", "CHAIR", "MD_CEO", "ED", "NED", "INED", "COMMITTEE", "COMPANY_SECRETARY"]


@pytest.fixture
def org(db_session, reference_seeded):
    o = Organisation(name="Review Test Plc", sector_key="insurance", country="NG")
    db_session.add(o)
    db_session.flush()
    link_sector_defaults(db_session, o)
    return o


def _proposal(db, org, key, value, excerpt="quoted text from the document") -> OrganisationFact:
    f = OrganisationFact(organisation_id=org.id, key=key, value=value, source="client", status="proposed",
                         origin="ai_extraction", source_excerpt=excerpt)
    db.add(f)
    db.flush()
    return f


# ----------------------------
# Review rules
# ----------------------------

def test_cannot_mark_reviewed_with_open_proposals(db_session, org) -> None:
    _proposal(db_session, org, "board_size", 9)
    with pytest.raises(review.ReviewError, match="open proposals"):
        review.mark_reviewed(db_session, org)
    db_session.add(OrgCommittee(organisation_id=org.id, name="Audit", committee_type="audit", source="client",
                                status="proposed", origin="ai_extraction"))
    db_session.flush()
    assert review.open_proposals(db_session, org) == {"facts": 1, "committees": 1}


def test_reviewing_bumps_version(db_session, org) -> None:
    review.add_fact(db_session, org, key="board_size", value=9, source="client")
    assert (org.profile_status, org.profile_version) == ("draft", 1)
    review.mark_reviewed(db_session, org)
    assert (org.profile_status, org.profile_version) == ("reviewed", 2)
    assert org.profile_reviewed_at is not None
    review.mark_reviewed(db_session, org)
    assert org.profile_version == 3


def test_editing_confirmed_fact_resets_to_draft(db_session, org) -> None:
    fact = review.add_fact(db_session, org, key="board_size", value=9, source="client")
    review.mark_reviewed(db_session, org)
    review.update_fact(db_session, org, fact, value=10)
    assert fact.value == 10 and org.profile_status == "draft"


def test_committee_change_resets_to_draft(db_session, org) -> None:
    c = review.add_committee(db_session, org, {"name": "Audit Committee", "committee_type": "audit"})
    review.mark_reviewed(db_session, org)
    review.update_committee(db_session, org, c, {"chair_name": "New Chair"})
    assert org.profile_status == "draft"
    review.mark_reviewed(db_session, org)
    review.delete_committee(db_session, org, c)
    assert org.profile_status == "draft"


def test_editing_a_proposal_confirms_it(db_session, org) -> None:
    p = _proposal(db_session, org, "board_size", 9)
    f = review.update_fact(db_session, org, p, value=11)
    assert (f.status, f.value) == ("confirmed", 11)
    assert "Edited" in (f.note or "")


def test_confirming_replaces_confirmed_value(db_session, org) -> None:
    review.add_fact(db_session, org, key="board_size", value=9, source="client")
    p = _proposal(db_session, org, "board_size", 10, excerpt="The Board has ten members")
    f = review.confirm_fact(db_session, org, p)
    rows = db_session.execute(select(OrganisationFact).where(
        OrganisationFact.organisation_id == org.id, OrganisationFact.key == "board_size")).scalars().all()
    assert len(rows) == 1 and rows[0].id == f.id
    assert (f.value, f.status, f.source_excerpt, f.origin) == (10, "confirmed", "The Board has ten members", "ai_extraction")


def test_reject_rules(db_session, org) -> None:
    p = _proposal(db_session, org, "ownership", "Family owned")
    assert review.reject_fact(db_session, org, p).status == "rejected"
    confirmed = review.add_fact(db_session, org, key="board_size", value=9, source="client")
    with pytest.raises(review.ReviewError):
        review.reject_fact(db_session, org, confirmed)
    with pytest.raises(review.ReviewError):
        review.update_fact(db_session, org, p, value="x")


def test_invalid_values_rejected(db_session, org) -> None:
    from app.domain.org_profile import FactValueError

    with pytest.raises(FactValueError):
        review.add_fact(db_session, org, key="board_size", value="nine", source="client")
    with pytest.raises(FactValueError):
        review.add_fact(db_session, org, key="board_composition", value={"aliens": 2}, source="client")
    with pytest.raises(review.ReviewError):
        review.add_fact(db_session, org, key="board_size", value=9, source="rumour")


def test_regulator_change_syncs_open_evaluations(db_session, org) -> None:
    ev_open = Evaluation(id="eval-reg-open", tenant_name="x", sector="x", year=2025, regulators={"items": []},
                         organisation_id=org.id, status="draft")
    ev_closed = Evaluation(id="eval-reg-closed", tenant_name="x", sector="x", year=2024, regulators={"items": ["OLD"]},
                           organisation_id=org.id, status="closed")
    db_session.add_all([ev_open, ev_closed])
    db_session.flush()
    review.add_fact(db_session, org, key="regulator", value=["NAICOM", "FRC"], source="public")
    assert ev_open.regulators == {"items": ["NAICOM", "FRC"]} and ev_open.tenant_name == org.name
    assert ev_closed.regulators == {"items": ["OLD"]}


# ----------------------------
# Snapshots
# ----------------------------

def test_snapshot_captures_context(db_session, org, tmp_storage) -> None:
    from app.services.org_documents import save_org_document

    doc = save_org_document(db_session, tmp_storage, org, doc_type="company_profile", filename="p.txt", data=b"Profile")
    review.add_fact(db_session, org, key="board_size", value=9, source="client")
    _proposal(db_session, org, "ownership", "not confirmed")  # proposals are not part of the context
    review.add_committee(db_session, org, {"name": "Audit Committee", "committee_type": "audit",
                                           "chair_name": "Ada", "member_names": ["Tunde"]})
    ev = Evaluation(id="eval-snap", tenant_name=org.name, sector="insurance", year=2025, regulators={"items": []},
                    organisation_id=org.id)
    db_session.add(ev)
    db_session.flush()
    apply_evaluation_code_defaults(db_session, ev)

    snap = review.snapshot_context(db_session, "eval-snap")
    assert snap.profile_version == org.profile_version
    assert [f["key"] for f in snap.facts] == ["board_size"] and snap.facts[0]["source"] == "client"
    assert snap.committees[0]["name"] == "Audit Committee" and snap.committees[0]["member_names"] == ["Tunde"]
    assert snap.document_ids == [str(doc.id)]
    assert {c["code"] for c in snap.governance_codes} == {"NCCG_2018", "NAICOM_2021"}


# ----------------------------
# Governance codes
# ----------------------------

def test_sector_defaults_on_create_and_sector_change(db_session, org) -> None:
    from app.services.organisations import organisation_codes, set_organisation_codes

    assert {(c.code, c.source) for c in organisation_codes(db_session, org)} == {
        ("NCCG_2018", "sector_default"), ("NAICOM_2021", "sector_default")}
    set_organisation_codes(db_session, org, ["NCCG_2018", "NAICOM_2021", "SEC_2011"])
    org.sector_key, org.sector_sub_type = "banking", "microfinance"
    link_sector_defaults(db_session, org)
    assert {(c.code, c.source) for c in organisation_codes(db_session, org)} == {
        ("NCCG_2018", "sector_default"), ("CBN_MFB_2018", "sector_default"), ("SEC_2011", "manual")}


def test_apply_defaults_uses_organisation_codes(db_session, org) -> None:
    from app.services.organisations import set_organisation_codes

    set_organisation_codes(db_session, org, ["NCCG_2018", "SEC_2011"])
    ev = Evaluation(id="eval-codes-org", tenant_name=org.name, sector="insurance", year=2025, regulators={"items": []},
                    organisation_id=org.id)
    db_session.add(ev)
    db_session.flush()
    result = apply_evaluation_code_defaults(db_session, ev)
    assert result["basis"] == "organisation"
    assert {c["code"] for c in result["codes"]} == {"NCCG_2018", "SEC_2011"}  # NAICOM was removed from the org


def test_apply_defaults_falls_back_to_sector(db_session, reference_seeded) -> None:
    ev = Evaluation(id="eval-codes-legacy", tenant_name="Legacy", sector="Pension", year=2025, regulators={"items": []})
    db_session.add(ev)
    db_session.flush()
    db_session.add(EvaluationGovernanceCode(evaluation_id=ev.id, code="SEC_2011", source="manual"))
    db_session.flush()
    result = apply_evaluation_code_defaults(db_session, ev)
    assert result["basis"] == "sector_default"
    assert {(c["code"], c["source"]) for c in result["codes"]} == {
        ("NCCG_2018", "sector_default"), ("PENCOM_2025", "sector_default"), ("SEC_2011", "manual")}


# ----------------------------
# API
# ----------------------------

def _new_org(api_client, name="API Insurance Plc", sector="Insurance"):
    res = api_client.post("/api/v1/organisations", json={"name": name, "sector": sector})
    assert res.status_code == 201, res.text
    return res.json()


def test_api_organisation_create_links_defaults(api_client, reference_seeded) -> None:
    org = _new_org(api_client)
    assert org["sector_key"] == "insurance" and org["profile_status"] == "draft" and org["profile_version"] == 1
    codes = api_client.get(f"/api/v1/organisations/{org['organisation_id']}/governance-codes").json()["items"]
    assert {(c["code"], c["source"]) for c in codes} == {("NCCG_2018", "sector_default"), ("NAICOM_2021", "sector_default")}
    assert api_client.post("/api/v1/organisations", json={"name": "api insurance plc"}).status_code == 409
    assert api_client.post("/api/v1/organisations", json={"name": "X", "sector": "Oil & Gas"}).status_code == 400

    put = api_client.put(f"/api/v1/organisations/{org['organisation_id']}/governance-codes",
                         json={"codes": ["NCCG_2018", "SEC_2011"]}).json()["items"]
    assert {(c["code"], c["source"]) for c in put} == {("NCCG_2018", "sector_default"), ("SEC_2011", "manual")}
    assert api_client.put(f"/api/v1/organisations/{org['organisation_id']}/governance-codes",
                          json={"codes": ["NOPE"]}).status_code == 400


def test_api_evaluation_create_requires_organisation(api_client, reference_seeded) -> None:
    assert api_client.post("/api/v1/evaluations", json={"tenant_name": "Old style", "sector": "insurance",
                                                        "year": 2025}).status_code == 400
    org = _new_org(api_client)
    api_client.post(f"/api/v1/organisations/{org['organisation_id']}/facts",
                    json={"key": "regulator", "value": ["NAICOM"], "source": "public"})
    res = api_client.post("/api/v1/evaluations", json={
        "organisation_id": org["organisation_id"],
        "review_period_start": "2025-01-01", "review_period_end": "2025-12-31", "deadline": "2026-03-31",
        "brief": "Annual review",
    })
    assert res.status_code == 201, res.text
    ev = res.json()
    assert ev["evaluation_id"].startswith("eval-")
    assert (ev["tenant_name"], ev["sector"], ev["regulators"]) == ("API Insurance Plc", "insurance", ["NAICOM"])
    assert ev["name"] == "2025 Board Evaluation" and ev["year"] == 2025 and ev["status"] == "draft"
    assert ev["subject_type_codes"] == ALL_SUBJECT_TYPES
    got = api_client.get(f"/api/v1/evaluations/{ev['evaluation_id']}").json()
    assert got["deadline"] == "2026-03-31" and got["organisation"]["name"] == "API Insurance Plc"

    bad = api_client.post("/api/v1/evaluations", json={"organisation_id": org["organisation_id"],
                                                       "review_period_start": "2025-12-31", "review_period_end": "2025-01-01"})
    assert bad.status_code == 400
    assert api_client.post("/api/v1/evaluations", json={"organisation_id": org["organisation_id"],
                                                       "subject_type_codes": ["BOARD", "NOPE"]}).status_code == 400


def test_api_evaluation_update_and_org_switch(api_client, reference_seeded) -> None:
    a = _new_org(api_client, "Alpha Insurance")
    b = _new_org(api_client, "Beta Bank", "Commercial Bank")
    ev = api_client.post("/api/v1/evaluations", json={"organisation_id": a["organisation_id"],
                                                      "subject_type_codes": ["BOARD", "CHAIR"]}).json()
    assert ev["subject_type_codes"] == ["BOARD", "CHAIR"]
    upd = api_client.patch(f"/api/v1/evaluations/{ev['evaluation_id']}", json={
        "organisation_id": b["organisation_id"], "name": "Renamed", "status": "in_review",
        "subject_type_codes": ["BOARD"]}).json()
    assert (upd["tenant_name"], upd["sector"], upd["name"], upd["status"]) == ("Beta Bank", "banking", "Renamed", "in_review")
    assert upd["subject_type_codes"] == ["BOARD"]

    renamed = api_client.patch(f"/api/v1/organisations/{b['organisation_id']}", json={"name": "Beta Bank Plc"}).json()
    assert renamed["name"] == "Beta Bank Plc"
    assert api_client.get(f"/api/v1/evaluations/{ev['evaluation_id']}").json()["tenant_name"] == "Beta Bank Plc"


def test_api_documents_and_extraction_switch(api_client, reference_seeded, tmp_storage, monkeypatch) -> None:
    monkeypatch.delenv("AI_EXTRACTION_ENABLED", raising=False)
    org = _new_org(api_client)
    base = f"/api/v1/organisations/{org['organisation_id']}"
    up = api_client.post(f"{base}/documents", data={"doc_type": "board_structure"},
                         files={"file": ("../Board List.txt", io.BytesIO(b"The Board has nine directors."), "text/plain")})
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["filename"] == "Board List.txt" and doc["extraction_status"] == "done"
    assert tmp_storage.exists(next(iter(_keys(tmp_storage))))
    assert api_client.get(f"{base}/documents/{doc['document_id']}/download").content == b"The Board has nine directors."
    assert api_client.post(f"{base}/documents", data={"doc_type": "board_structure"},
                           files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")}).status_code == 400
    assert api_client.post(f"{base}/documents", data={"doc_type": "nonsense"},
                           files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}).status_code == 400

    ex = api_client.post(f"{base}/extraction")
    assert ex.status_code == 409 and "turned off" in ex.json()["detail"]

    assert api_client.delete(f"{base}/documents/{doc['document_id']}").status_code == 200
    assert list(_keys(tmp_storage)) == []
    assert api_client.get(f"{base}/documents").json()["count"] == 0


def _keys(storage):
    root = storage.root / "org-docs"
    return [f"org-docs/{p.name}" for p in root.glob("*")] if root.exists() else []


def test_api_review_flow(api_client, db_session, reference_seeded) -> None:
    org = _new_org(api_client)
    base = f"/api/v1/organisations/{org['organisation_id']}"
    o = db_session.get(Organisation, __import__("uuid").UUID(org["organisation_id"]))
    p = _proposal(db_session, o, "board_size", 9)

    blocked = api_client.post(f"{base}/mark-reviewed")
    assert blocked.status_code == 409 and "open proposals" in blocked.json()["detail"]

    confirmed = api_client.post(f"{base}/facts/{p.id}/confirm", json={"value": 8}).json()
    assert (confirmed["status"], confirmed["value"]) == ("confirmed", 8)
    reviewed = api_client.post(f"{base}/mark-reviewed").json()
    assert (reviewed["profile_status"], reviewed["profile_version"]) == ("reviewed", 2)

    api_client.patch(f"{base}/facts/{confirmed['fact_id']}", json={"value": 7})
    assert api_client.get(base).json()["profile_status"] == "draft"

    cm = api_client.post(f"{base}/committees", json={"name": "Risk Committee", "committee_type": "risk",
                                                     "member_names": ["A", "B", "A"]}).json()
    assert cm["status"] == "confirmed" and cm["member_names"] == ["A", "B"]
    assert api_client.post(f"{base}/committees", json={"name": "X", "committee_type": "fun"}).status_code == 400
    assert api_client.post(f"{base}/facts", json={"key": "nope", "value": 1, "source": "client"}).status_code == 400
    lst = api_client.get("/api/v1/organisations").json()["items"]
    assert any(i["name"] == "API Insurance Plc" for i in lst)
    reg = api_client.get("/api/v1/org-profile/registry").json()
    assert {f["key"] for f in reg["facts"]} >= {"regulator", "board_composition", "governance_context"}
    assert reg["ai_extraction_enabled"] is False


def test_api_context_endpoints(api_client, reference_seeded) -> None:
    org = _new_org(api_client)
    ev = api_client.post("/api/v1/evaluations", json={"organisation_id": org["organisation_id"]}).json()
    eid = ev["evaluation_id"]
    assert api_client.get(f"/api/v1/evaluations/{eid}/context").status_code == 404
    api_client.post(f"/api/v1/evaluations/{eid}/governance-codes/apply-defaults")
    snap = api_client.post(f"/api/v1/evaluations/{eid}/context/snapshot").json()
    latest = api_client.get(f"/api/v1/evaluations/{eid}/context").json()
    assert latest["snapshot_id"] == snap["snapshot_id"]
    assert {c["code"] for c in latest["governance_codes"]} == {"NCCG_2018", "NAICOM_2021"}

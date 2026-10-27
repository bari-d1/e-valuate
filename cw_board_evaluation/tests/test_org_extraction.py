"""
AI extraction with the LLM mocked: proposals need verbatim excerpts, re-runs
leave confirmed/manual facts alone, the setting blocks it, token cap is applied.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.db.models import Organisation, OrganisationFact, OrgCommittee, OrgDocument
from app.services import profile_review as review
from app.services.org_extraction import ExtractionDisabled, run_extraction

pytestmark = pytest.mark.integration

PROFILE = (
    "Acme Insurance Plc is regulated by the National Insurance Commission (NAICOM).\n\n"
    "The Board comprises nine directors, of whom three are independent non-executive directors.\n\n"
    "The Audit Committee is chaired by Mrs. Ada Obi. Members: Mr. Tunde Bello and Dr. Chi Eze."
)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("AI_EXTRACTION_ENABLED", "true")


@pytest.fixture
def org(db_session, reference_seeded):
    o = Organisation(name="Acme Insurance Plc", sector_key="insurance", country="NG")
    db_session.add(o)
    db_session.flush()
    return o


def _doc(db, org, text=PROFILE, doc_type="company_profile", name="profile.txt") -> OrgDocument:
    d = OrgDocument(organisation_id=org.id, doc_type=doc_type, filename=name, content_type="text/plain",
                    size_bytes=len(text), storage_key=f"org-docs/{uuid.uuid4().hex}.txt",
                    extracted_text=text, extraction_status="done")
    db.add(d)
    db.flush()
    return d


def fake_llm(reply: dict):
    calls = []

    def call(system: str, user: str) -> str:
        calls.append(user)
        return json.dumps(reply)

    call.calls = calls
    return call


GOOD = {
    "facts": [
        {"key": "board_size", "value": 9, "source_excerpt": "The Board comprises nine directors"},
        {"key": "regulator", "value": ["NAICOM"], "source_excerpt": "regulated by the National Insurance Commission (NAICOM)"},
        # excerpt not in the document -> dropped
        {"key": "ownership", "value": "Owned by Acme Holdings", "source_excerpt": "Acme Holdings owns 60% of the shares"},
        # number not stated in the excerpt -> dropped
        {"key": "years_in_operation", "value": 25, "source_excerpt": "Acme Insurance Plc is regulated by"},
        # unknown key -> dropped
        {"key": "favourite_colour", "value": "blue", "source_excerpt": "The Board comprises nine directors"},
        # null value: the model says unknown -> nothing proposed
        {"key": "listing_status", "value": None, "source_excerpt": "Acme Insurance Plc is regulated by"},
    ],
    "committees": [
        {"name": "Audit Committee", "committee_type": "audit", "chair_name": "Mrs. Ada Obi",
         "member_names": ["Mr. Tunde Bello", "Dr. Chi Eze", "Mr. Invented Person"],
         "source_excerpt": "The Audit Committee is chaired by Mrs. Ada Obi."},
        {"name": "Risk Committee", "committee_type": "risk", "member_names": [],
         "source_excerpt": "The Risk Committee meets quarterly."},
    ],
}


def _facts(db, org):
    return {f.key: f for f in db.execute(select(OrganisationFact).where(OrganisationFact.organisation_id == org.id)).scalars()}


def test_proposals_created_with_verified_excerpts(db_session, org, enabled) -> None:
    doc = _doc(db_session, org)
    result = run_extraction(db_session, org, llm_call=fake_llm(GOOD))

    facts = _facts(db_session, org)
    assert set(facts) == {"board_size", "regulator"}
    for f in facts.values():
        assert f.status == "proposed" and f.origin == "ai_extraction" and f.source == "client"
        assert f.source_document_id == doc.id
        assert f.source_excerpt and f.source_excerpt.lower() in PROFILE.lower()
    assert facts["board_size"].value == 9 and facts["regulator"].value == ["NAICOM"]

    committees = db_session.execute(select(OrgCommittee).where(OrgCommittee.organisation_id == org.id)).scalars().all()
    assert [c.name for c in committees] == ["Audit Committee"]  # Risk Committee isn't in the document
    audit = committees[0]
    assert audit.status == "proposed" and audit.chair_name == "Mrs. Ada Obi"
    assert audit.member_names == ["Mr. Tunde Bello", "Dr. Chi Eze"]  # invented name dropped

    reasons = {(d.get("key") or d.get("committee"), d["reason"]) for d in result.discarded}
    assert ("ownership", "excerpt not found in the document") in reasons
    assert ("years_in_operation", "number not stated in the excerpt") in reasons
    assert ("favourite_colour", "unknown fact key") in reasons
    assert ("Risk Committee", "excerpt not found in the document") in reasons
    assert any("Invented Person" in r for _, r in reasons)
    assert (result.facts_added, result.committees_added) == (2, 1)


def test_rerun_keeps_confirmed_and_manual(db_session, org, enabled) -> None:
    _doc(db_session, org)
    run_extraction(db_session, org, llm_call=fake_llm(GOOD))
    facts = _facts(db_session, org)
    review.confirm_fact(db_session, org, facts["board_size"])            # confirmed AI fact
    review.add_fact(db_session, org, key="regulator", value=["CBN"], source="consultant")  # manual

    second = dict(GOOD)
    second["facts"] = [
        {"key": "board_size", "value": 9, "source_excerpt": "The Board comprises nine directors"},
        {"key": "regulator", "value": ["NAICOM"], "source_excerpt": "regulated by the National Insurance Commission (NAICOM)"},
    ]
    result = run_extraction(db_session, org, llm_call=fake_llm(second))

    rows = db_session.execute(select(OrganisationFact).where(OrganisationFact.organisation_id == org.id)).scalars().all()
    by = {(f.key, f.status): f for f in rows}
    assert by[("board_size", "confirmed")].value == 9
    assert ("board_size", "proposed") not in by          # same as confirmed: nothing new
    assert by[("regulator", "confirmed")].value == ["CBN"] and by[("regulator", "confirmed")].origin == "manual"
    # the earlier AI proposal is left exactly as it was (the consultant resolves it); not refreshed
    assert by[("regulator", "proposed")].value == ["NAICOM"]
    assert result.facts_updated == 0
    assert result.facts_added == 0
    assert {u["reason"] for u in result.unchanged} >= {"matches the confirmed value", "a manual entry exists"}
    # the committee proposal from the first run is refreshed, not duplicated
    assert result.committees_updated == 1 and result.committees_added == 0


def test_rerun_updates_proposal_and_respects_rejections(db_session, org, enabled) -> None:
    _doc(db_session, org)
    run_extraction(db_session, org, llm_call=fake_llm(GOOD))
    regulator = _facts(db_session, org)["regulator"]
    review.reject_fact(db_session, org, regulator)

    result = run_extraction(db_session, org, llm_call=fake_llm(GOOD))
    statuses = [(f.key, f.status) for f in db_session.execute(
        select(OrganisationFact).where(OrganisationFact.organisation_id == org.id)).scalars()]
    assert ("regulator", "rejected") in statuses and ("regulator", "proposed") not in statuses
    assert result.facts_updated == 1  # board_size proposal refreshed


def test_disabled_setting_blocks_extraction(db_session, org, monkeypatch) -> None:
    monkeypatch.delenv("AI_EXTRACTION_ENABLED", raising=False)
    _doc(db_session, org)
    llm = fake_llm(GOOD)
    with pytest.raises(ExtractionDisabled):
        run_extraction(db_session, org, llm_call=llm)
    assert llm.calls == []


def test_long_documents_are_chunked_and_capped(db_session, org, enabled) -> None:
    long_text = ("Filler paragraph about operations. " * 30 + "\n\n") * 40 + PROFILE
    _doc(db_session, org, text=long_text, doc_type="annual_report", name="annual.txt")
    _doc(db_session, org, text=PROFILE, doc_type="board_structure", name="board.txt")
    llm = fake_llm({"facts": GOOD["facts"][:1], "committees": []})

    result = run_extraction(db_session, org, llm_call=llm, max_tokens=4000, chunk_tokens=1000)

    assert result.chunks_processed == len(llm.calls) >= 2
    assert result.estimated_tokens_used <= 4000
    assert any("token cap" in s["reason"] for s in result.skipped)
    # most useful document type goes first
    assert "Document type: board_structure" in llm.calls[0]
    # the same fact from several chunks/documents is proposed once
    assert result.facts_added == 1


def test_unreadable_reply_is_reported(db_session, org, enabled) -> None:
    _doc(db_session, org)
    result = run_extraction(db_session, org, llm_call=lambda s, u: "not json")
    assert result.facts_added == 0
    assert any("unreadable" in d["reason"] for d in result.discarded)


CHARTER = "The Board shall have between seven and eleven directors. The Company is regulated by NAICOM."
REPORT = (
    "As at 31 December 2025 the Board had eight members.\n\n"
    "Acme Insurance Plc is regulated by the National Insurance Commission (NAICOM).\n\n"
    "On 1 April 2025 a new Managing Director took office.\n\n"
    "In May 2025 the regulator fined the Company for late filing of returns.\n\n"
    "The Company is owned by Acme Holdings, which holds 51% of the shares."
)
REPLIES = {
    "charter.txt": {"facts": [
        {"key": "board_size", "value": 7, "source_excerpt": "The Board shall have between seven and eleven directors."},
        {"key": "regulator", "value": ["NAICOM"], "source_excerpt": "The Company is regulated by NAICOM."},
        {"key": "ownership", "value": "Regulated by NAICOM", "source_excerpt": "The Company is regulated by NAICOM."},
    ]},
    "report.txt": {"facts": [
        {"key": "board_size", "value": 8, "source_excerpt": "As at 31 December 2025 the Board had eight members."},
        {"key": "regulator", "value": ["National Insurance Commission (NAICOM)"],
         "source_excerpt": "regulated by the National Insurance Commission (NAICOM)"},
        # one entry per list item, each with its own quote
        {"key": "recent_events", "value": ["New Managing Director from 1 April 2025"],
         "source_excerpt": "On 1 April 2025 a new Managing Director took office."},
        {"key": "recent_events", "value": ["Regulatory fine for late filing, May 2025"],
         "source_excerpt": "In May 2025 the regulator fined the Company for late filing of returns."},
        {"key": "ownership", "value": "Acme Holdings, 51%",
         "source_excerpt": "The Company is owned by Acme Holdings, which holds 51% of the shares."},
    ]},
}


def test_ranges_are_not_counts_and_lists_merge_cleanly(db_session, org, enabled) -> None:
    _doc(db_session, org, CHARTER, doc_type="governance_policy", name="charter.txt")  # read first
    _doc(db_session, org, REPORT, doc_type="annual_report", name="report.txt")

    def llm(system, user):
        return json.dumps(next(r for name, r in REPLIES.items() if f"Document: {name}" in user))

    result = run_extraction(db_session, org, llm_call=llm)
    facts = _facts(db_session, org)
    assert facts["board_size"].value == 8
    assert facts["board_size"].source_excerpt == "As at 31 December 2025 the Board had eight members."
    assert {"key": "board_size", "label": "Board size", "filename": "charter.txt",
            "reason": "the quote states a rule or range, not an actual number"} in result.discarded
    assert facts["regulator"].value == ["National Insurance Commission (NAICOM)"]
    assert facts["recent_events"].value == ["New Managing Director from 1 April 2025",
                                            "Regulatory fine for late filing, May 2025"]
    # Alternatives are listed as plain text, not JSON with escaped quotes
    assert facts["ownership"].note == "Other values found: “Acme Holdings, 51%” (report.txt)"

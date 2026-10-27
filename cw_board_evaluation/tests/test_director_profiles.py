"""
Director profiles: review rules, role sync, AI extraction (LLM mocked),
committee matching, participants from board members, readiness, snapshots
and the board member API.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.db.models import (
    BoardMember,
    BoardMemberFact,
    CommitteeMembership,
    Evaluation,
    Organisation,
    OrgCommittee,
    OrgDocument,
    Participant,
)
from app.services import board_members as svc
from app.services import profile_review as review
from app.services.committee_matching import match_committee_members
from app.services.member_extraction import run_member_extraction
from app.services.org_extraction import ExtractionDisabled

pytestmark = pytest.mark.integration

CV = (
    "Board Member 07 was appointed to the Board on 1 June 2015 as an Independent Non-Executive Director.\n\n"
    "She holds no shares in the Company and has no business relationship with it.\n\n"
    "A chartered accountant (FCA), she previously served as Finance Director of a logistics group.\n\n"
    "Colleagues describe her as direct and well prepared."
)


@pytest.fixture
def org(db_session, reference_seeded):
    o = Organisation(name="Profiles Test Plc", sector_key="insurance", country="NG")
    db_session.add(o)
    db_session.flush()
    return o


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("AI_EXTRACTION_ENABLED", "true")


def _member(db, org, name="Board Member 07", email="member07@demo.test", code="P007") -> BoardMember:
    return svc.create_member(db, org, full_name=name, email=email, display_code=code)


def _evaluation(db, org, eid, status="draft") -> Evaluation:
    ev = Evaluation(id=eid, tenant_name=org.name, sector="insurance", year=2025, regulators={"items": []},
                    organisation_id=org.id, status=status)
    db.add(ev)
    db.flush()
    return ev


def _participant(db, ev, m=None, role=None, email=None) -> Participant:
    p = Participant(evaluation_id=ev.id, email=email or (m.email if m else f"{uuid.uuid4().hex[:6]}@demo.test"),
                    full_name=m.full_name if m else "Unlinked Person", role=role, status="invited",
                    board_member_id=m.id if m else None)
    db.add(p)
    db.flush()
    return p


def _proposal(db, m, key, value, excerpt="quoted") -> BoardMemberFact:
    f = BoardMemberFact(board_member_id=m.id, key=key, value=value, source="client", status="proposed",
                        origin="ai_extraction", source_excerpt=excerpt)
    db.add(f)
    db.flush()
    return f


def _committee(db, org, name, chair=None, members=(), status="confirmed") -> OrgCommittee:
    c = OrgCommittee(organisation_id=org.id, name=name, committee_type="audit", source="client", status=status,
                     origin="manual", chair_name=chair, member_names=list(members))
    db.add(c)
    db.flush()
    return c


def _facts(db, m):
    return {(f.key, f.status): f for f in db.execute(
        select(BoardMemberFact).where(BoardMemberFact.board_member_id == m.id)).scalars()}


# ----------------------------
# Members
# ----------------------------

def test_member_uniqueness(db_session, org) -> None:
    m = _member(db_session, org, email=" Member07@Demo.test ", code="p007")
    assert (m.email, m.display_code) == ("member07@demo.test", "P007")
    with pytest.raises(review.ReviewError, match="email"):
        _member(db_session, org, name="Other", email="MEMBER07@demo.test", code="P008")
    with pytest.raises(review.ReviewError, match="Display code"):
        _member(db_session, org, name="Other", email="other@demo.test", code="P007")
    other_org = Organisation(name="Another Plc", country="NG")
    db_session.add(other_org)
    db_session.flush()
    _member(db_session, other_org)  # same email and code in another company is fine


# ----------------------------
# Review rules
# ----------------------------

def test_mark_reviewed_needs_role_and_no_open_proposals(db_session, org) -> None:
    m = _member(db_session, org)
    with pytest.raises(review.ReviewError, match="governance role"):
        svc.mark_member_reviewed(db_session, m)
    svc.add_member_fact(db_session, m, key="governance_role", value="ined", source="consultant")
    p = _proposal(db_session, m, "qualifications", ["FCA"])
    with pytest.raises(review.ReviewError, match="open proposals"):
        svc.mark_member_reviewed(db_session, m)
    svc.confirm_member_fact(db_session, m, p)

    c = _committee(db_session, org, "Audit Committee")
    db_session.add(CommitteeMembership(committee_id=c.id, board_member_id=m.id, membership_role="member",
                                       source="client", status="proposed", origin="name_match"))
    db_session.flush()
    assert svc.open_proposals(db_session, m) == {"facts": 0, "memberships": 1}
    with pytest.raises(review.ReviewError, match="1 committee link"):
        svc.mark_member_reviewed(db_session, m)


def test_reviewing_bumps_version_and_changes_reset_to_draft(db_session, org) -> None:
    m = _member(db_session, org)
    role = svc.add_member_fact(db_session, m, key="governance_role", value="ned", source="consultant")
    svc.mark_member_reviewed(db_session, m)
    assert (m.profile_status, m.profile_version) == ("reviewed", 2) and m.profile_reviewed_at
    svc.update_member_fact(db_session, m, role, value="ined")
    assert m.profile_status == "draft"

    svc.mark_member_reviewed(db_session, m)
    assert m.profile_version == 3
    c = _committee(db_session, org, "Risk Committee")
    ms = svc.add_membership(db_session, c, m, membership_role="chair")
    assert m.profile_status == "draft" and ms.status == "confirmed"

    svc.mark_member_reviewed(db_session, m)
    svc.update_member(db_session, m, {"display_code": "P070"})
    assert m.profile_status == "draft"


# ----------------------------
# Role sync
# ----------------------------

def test_confirmed_role_updates_draft_evaluations_only(db_session, org) -> None:
    m = _member(db_session, org)
    draft = _participant(db_session, _evaluation(db_session, org, "eval-sync-draft"), m, role="NED")
    live = _participant(db_session, _evaluation(db_session, org, "eval-sync-live", status="live"), m, role="NED")
    closed = _participant(db_session, _evaluation(db_session, org, "eval-sync-closed", status="closed"), m, role="NED")

    p = _proposal(db_session, m, "governance_role", "ined")
    assert draft.role == "NED"  # a proposal changes nothing
    svc.confirm_member_fact(db_session, m, p)
    assert (draft.role, live.role, closed.role) == ("INED", "NED", "NED")

    svc.add_member_fact(db_session, m, key="governance_role", value="chair", source="consultant")
    assert (draft.role, live.role) == ("Chair", "NED")


# ----------------------------
# Extraction (LLM mocked)
# ----------------------------

def _cv(db, org, m, text=CV) -> OrgDocument:
    d = OrgDocument(organisation_id=org.id, board_member_id=m.id, doc_type="director_profile", filename="cv.txt",
                    content_type="text/plain", size_bytes=len(text), storage_key=f"org-docs/{uuid.uuid4().hex}.txt",
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


REPLY = {
    "facts": [
        {"key": "governance_role", "value": "ined",
         "source_excerpt": "as an Independent Non-Executive Director"},
        {"key": "board_appointment_date", "value": "2015-06-01",
         "source_excerpt": "was appointed to the Board on 1 June 2015"},
        {"key": "qualifications", "value": ["FCA"], "source_excerpt": "A chartered accountant (FCA)"},
        # explicit statement: proposed
        {"key": "holds_company_shares", "value": {"answer": "no"},
         "source_excerpt": "She holds no shares in the Company"},
        # unknown answers are never proposed
        {"key": "provides_advisory_services", "value": {"answer": "unknown"},
         "source_excerpt": "She holds no shares in the Company"},
        # excerpt not in the document: dropped
        {"key": "employee_of_company_or_group_last_5y", "value": {"answer": "no"},
         "source_excerpt": "She has never been employed by the group"},
        # the model's own characterisation: dropped
        {"key": "personality_notes", "value": "A collaborative and thoughtful leader",
         "source_excerpt": "Colleagues describe her as direct and well prepared."},
        # date not in the excerpt: dropped
        {"key": "board_appointment_date", "value": "2016-01-01", "source_excerpt": "appointed to the Board"},
    ],
}


def test_extraction_proposes_with_verbatim_excerpts(db_session, org, enabled) -> None:
    m = _member(db_session, org)
    doc = _cv(db_session, org, m)
    llm = fake_llm(REPLY)
    result = run_member_extraction(db_session, m, llm_call=llm)

    facts = _facts(db_session, m)
    assert {k for k, _ in facts} == {"governance_role", "board_appointment_date", "qualifications",
                                     "holds_company_shares"}
    for f in facts.values():
        assert f.status == "proposed" and f.origin == "ai_extraction" and f.source_document_id == doc.id
        assert f.source_excerpt.lower() in CV.lower()
    assert facts[("holds_company_shares", "proposed")].value["answer"] == "no"
    assert "Board Member 07" in llm.calls[0]
    reasons = {(d["key"], d["reason"]) for d in result.discarded}
    assert ("employee_of_company_or_group_last_5y", "excerpt not found in the document") in reasons
    assert ("personality_notes", "notes must be a verbatim quote from the document") in reasons
    assert ("board_appointment_date", "date not stated in the excerpt") in reasons
    # independence not stated explicitly stays unknown
    assert svc.confirmed_facts(db_session, m) == {}


def test_personality_notes_only_as_quotes(db_session, org, enabled) -> None:
    m = _member(db_session, org)
    _cv(db_session, org, m)
    quote = "direct and well prepared"
    run_member_extraction(db_session, m, llm_call=fake_llm({"facts": [
        {"key": "personality_notes", "value": quote, "source_excerpt": "Colleagues describe her as direct and well prepared."},
    ]}))
    assert _facts(db_session, m)[("personality_notes", "proposed")].value == quote


def test_rerun_keeps_confirmed_facts(db_session, org, enabled) -> None:
    m = _member(db_session, org)
    _cv(db_session, org, m)
    run_member_extraction(db_session, m, llm_call=fake_llm(REPLY))
    facts = _facts(db_session, m)
    svc.confirm_member_fact(db_session, m, facts[("governance_role", "proposed")])
    svc.add_member_fact(db_session, m, key="qualifications", value=["FCA", "MBA"], source="consultant")
    svc.reject_member_fact(db_session, m, facts[("holds_company_shares", "proposed")])

    result = run_member_extraction(db_session, m, llm_call=fake_llm(REPLY))
    facts = _facts(db_session, m)
    assert facts[("governance_role", "confirmed")].value == "ined"
    assert ("governance_role", "proposed") not in facts
    assert facts[("qualifications", "confirmed")].value == ["FCA", "MBA"]
    assert ("holds_company_shares", "rejected") in facts and ("holds_company_shares", "proposed") not in facts
    assert result.facts_added == 0


def test_setting_blocks_extraction(db_session, org, monkeypatch) -> None:
    monkeypatch.delenv("AI_EXTRACTION_ENABLED", raising=False)
    m = _member(db_session, org)
    _cv(db_session, org, m)
    llm = fake_llm(REPLY)
    with pytest.raises(ExtractionDisabled):
        run_member_extraction(db_session, m, llm_call=llm)
    assert llm.calls == []


def test_company_extraction_skips_member_documents(db_session, org, enabled) -> None:
    from app.services.org_extraction import run_extraction

    m = _member(db_session, org)
    _cv(db_session, org, m)
    llm = fake_llm({"facts": [], "committees": []})
    run_extraction(db_session, org, llm_call=llm)
    assert llm.calls == []


# ----------------------------
# Committee matching
# ----------------------------

def test_committee_matching(db_session, org) -> None:
    ada = _member(db_session, org, "Ada Obi", "ada@demo.test", "P001")
    tunde = _member(db_session, org, "Tunde Bello", "tunde@demo.test", "P002")
    _member(db_session, org, "Chi Eze", "chi@demo.test", "P003")
    _member(db_session, org, "Ngozi Okafor", "ngozi1@demo.test", "P004")
    _member(db_session, org, "Ngozi Okafor", "ngozi2@demo.test", "P005")
    audit = _committee(db_session, org, "Audit Committee", chair="Chief (Mrs.) Ada OBI",
                       members=["Mrs. Ada Obi", "Mr Tunde Bello.", "Dr. Chi Ezeh", "Mr. Nobody Known", "Ngozi Okafor"])
    _committee(db_session, org, "Risk Committee", chair="Ada Obi", status="proposed")

    result = match_committee_members(db_session, org)
    proposed = {(e["name"], e["membership_role"]) for e in result["proposed"]}
    assert proposed == {("Chief (Mrs.) Ada OBI", "chair"), ("Mr Tunde Bello.", "member")}
    near = {e["name"]: e for e in result["near_misses"]}
    assert set(near) == {"Dr. Chi Ezeh", "Ngozi Okafor"}
    assert near["Dr. Chi Ezeh"]["candidates"][0]["board_member"] == "P003 · Chi Eze"
    assert near["Ngozi Okafor"]["reason"] == "several board members have this name"
    assert [e["name"] for e in result["unmatched"]] == ["Mr. Nobody Known"]
    assert result["skipped_committees"] == [{"committee": "Risk Committee", "reason": "committee is proposed"}]

    links = db_session.execute(select(CommitteeMembership).where(
        CommitteeMembership.committee_id == audit.id)).scalars().all()
    assert {(ms.board_member_id, ms.membership_role, ms.status) for ms in links} == {
        (ada.id, "chair", "proposed"), (tunde.id, "member", "proposed")}

    # confirm one, reject the other; a re-run changes neither and adds nothing
    by_member = {ms.board_member_id: ms for ms in links}
    svc.confirm_membership(db_session, by_member[ada.id])
    svc.reject_membership(db_session, by_member[tunde.id])
    again = match_committee_members(db_session, org)
    assert again["proposed"] == []
    assert {(e["name"], e["status"]) for e in again["already_linked"]} == {
        ("Chief (Mrs.) Ada OBI", "confirmed"), ("Mr Tunde Bello.", "rejected")}
    [linked] = svc.member_committees(db_session, ada)
    assert linked["membership_role"] == "chair"


# ----------------------------
# Evaluations: participants, readiness, snapshot
# ----------------------------

def _ready_member(db, org, **kw) -> BoardMember:
    m = _member(db, org, **kw)
    svc.add_member_fact(db, m, key="governance_role", value="ned", source="consultant")
    svc.mark_member_reviewed(db, m)
    return m


def test_from_board_members_sends_nothing(api_client, db_session, org, monkeypatch) -> None:
    import app.api.evaluations as evaluations_api

    def no_send(*a, **kw):
        raise AssertionError("from-board-members must not send email")

    monkeypatch.setattr(evaluations_api, "send_invite_email", no_send)
    ev = _evaluation(db_session, org, "eval-from-members")
    m = _ready_member(db_session, org)
    no_email = _member(db_session, org, "Board Member 08", None, "P008")
    gone = _member(db_session, org, "Board Member 09", "member09@demo.test", "P009")
    svc.update_member(db_session, gone, {"active": False})
    _participant(db_session, ev, email="MEMBER07@demo.test")  # already invited by email, not yet linked
    db_session.commit()

    res = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/from-board-members")
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["created"], body["existing"], body["emails_sent"]) == (1, 1, 0)
    assert body["placeholder_emails"] == ["p008@example.invalid"]
    rows = {p.email: p for p in db_session.execute(
        select(Participant).where(Participant.evaluation_id == ev.id)).scalars()}
    assert set(rows) == {"MEMBER07@demo.test", "p008@example.invalid"}
    assert rows["MEMBER07@demo.test"].board_member_id == m.id
    assert rows["p008@example.invalid"].board_member_id == no_email.id and rows["p008@example.invalid"].role is None

    again = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/from-board-members").json()
    assert (again["created"], again["existing"]) == (0, 2)
    picked = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/from-board-members",
                             json={"board_member_ids": [str(gone.id)]}).json()
    assert picked["created"] == 1

    listed = api_client.get(f"/api/v1/evaluations/{ev.id}/participants").json()
    items = listed["items"] if isinstance(listed, dict) else listed
    assert {i.get("display_code") for i in items} == {"P007", "P008", "P009"}


def test_readiness_reasons(api_client, db_session, org) -> None:
    ev = _evaluation(db_session, org, "eval-ready")
    ready = _ready_member(db_session, org)
    no_role = _member(db_session, org, "Board Member 08", "member08@demo.test", "P008")
    review_due = _member(db_session, org, "Board Member 09", "member09@demo.test", "P009")
    svc.add_member_fact(db_session, review_due, key="governance_role", value="ined", source="consultant")
    for m in (ready, no_role, review_due):
        _participant(db_session, ev, m)
    _participant(db_session, ev)
    db_session.commit()

    res = api_client.get(f"/api/v1/evaluations/{ev.id}/readiness")
    assert res.status_code == 200, res.text
    body = res.json()
    items = {i["label"]: i for i in (body["items"] if isinstance(body, dict) else body)}
    assert items["P007 · Board Member 07"]["status"] == "ready"
    assert items["P007 · Board Member 07"]["blocking_reasons"] == []
    assert items["P008 · Board Member 08"]["status"] == "missing_role"
    assert "No confirmed governance role." in items["P008 · Board Member 08"]["blocking_reasons"]
    due = items["P009 · Board Member 09"]
    assert due["status"] == "needs_review" and due["blocking_reasons"] == ["Profile not marked reviewed."]
    assert due["warnings"] == ["Independent NED with every independence question unknown."]
    assert items["Unlinked Person"]["status"] == "not_linked"


def test_snapshot_keeps_generation_only_separate(db_session, org) -> None:
    ev = _evaluation(db_session, org, "eval-snap-members")
    m = _ready_member(db_session, org)
    svc.add_member_fact(db_session, m, key="board_appointment_date", value="2015-06-01", source="client")
    svc.add_member_fact(db_session, m, key="personality_notes", value="direct and well prepared", source="client")
    _proposal(db_session, m, "qualifications", ["FCA"])  # proposals are not part of the snapshot
    p = _participant(db_session, ev, m, role="NED")

    snap = review.snapshot_context(db_session, ev.id)
    [entry] = snap.participants
    assert entry["participant_id"] == str(p.id) and entry["display_code"] == "P007"
    assert {f["key"] for f in entry["facts"]} == {"governance_role", "board_appointment_date"}
    assert entry["tenure"]["exceeds_limit"] is True
    assert "personality_notes" not in json.dumps(snap.participants)
    assert [f["key"] for f in snap.generation_only[str(p.id)]] == ["personality_notes"]


# ----------------------------
# API
# ----------------------------

def test_api_board_members(api_client, db_session, org, tmp_storage, monkeypatch) -> None:
    monkeypatch.delenv("AI_EXTRACTION_ENABLED", raising=False)
    db_session.commit()
    base = f"/api/v1/organisations/{org.id}/board-members"
    res = api_client.post(base, json={"full_name": "Board Member 07", "email": "member07@demo.test", "display_code": "p007"})
    assert res.status_code == 201, res.text
    m = res.json()
    assert (m["label"], m["profile_status"], m["ai_extraction_enabled"]) == ("P007 · Board Member 07", "draft", False)
    assert "No confirmed role" in m["problems"]
    assert api_client.post(base, json={"full_name": "Dup", "email": "MEMBER07@demo.test"}).status_code == 400
    mid = m["board_member_id"]

    up = api_client.post(f"{base}/{mid}/documents", files={"file": ("cv.txt", b"Board Member 07 CV", "text/plain")})
    assert up.status_code == 201, up.text
    assert up.json()["doc_type"] == "director_profile"
    assert api_client.get(f"{base}/{mid}/documents").json()["count"] == 1
    assert api_client.get(f"/api/v1/organisations/{org.id}/documents").json()["count"] == 0  # not a company doc
    assert api_client.post(f"{base}/{mid}/extraction").status_code == 409

    blocked = api_client.post(f"{base}/{mid}/mark-reviewed")
    assert blocked.status_code == 409 and "governance role" in blocked.json()["detail"]
    fact = api_client.post(f"{base}/{mid}/facts", json={"key": "governance_role", "value": "ined", "source": "consultant"})
    assert fact.status_code == 201, fact.text
    assert api_client.post(f"{base}/{mid}/facts", json={"key": "governance_role", "value": "boss",
                                                         "source": "consultant"}).status_code == 400
    reviewed = api_client.post(f"{base}/{mid}/mark-reviewed").json()
    assert (reviewed["profile_status"], reviewed["profile_version"]) == ("reviewed", 2)
    assert reviewed["independence"]["holds_company_shares"] == {"answer": "unknown"}

    listed = api_client.get(base).json()["items"]
    assert [(i["label"], i["governance_role"], i["problems"]) for i in listed] == [
        ("P007 · Board Member 07", "ined", ["Independence unknown"])]

    committee = api_client.post(f"/api/v1/organisations/{org.id}/committees",
                                json={"name": "Audit Committee", "committee_type": "audit",
                                      "chair_name": "Board Member 07"}).json()
    match = api_client.post(f"/api/v1/organisations/{org.id}/committee-memberships/match").json()
    assert [e["name"] for e in match["proposed"]] == ["Board Member 07"]
    links = api_client.get(f"/api/v1/organisations/{org.id}/committee-memberships?status=proposed").json()["items"]
    assert links[0]["membership_role"] == "chair" and links[0]["committee_id"] == committee["committee_id"]
    assert api_client.get(f"{base}/{mid}").json()["profile_status"] == "reviewed"
    ok = api_client.post(f"/api/v1/organisations/{org.id}/committee-memberships/{links[0]['membership_id']}/confirm")
    assert ok.status_code == 200 and ok.json()["status"] == "confirmed"
    got = api_client.get(f"{base}/{mid}").json()
    assert got["committees"][0]["membership_role"] == "chair" and got["profile_status"] == "draft"

    gone = api_client.post(f"{base}/{mid}/deactivate").json()
    assert gone["active"] is False
    assert api_client.get(f"{base}?include_inactive=false").json()["count"] == 0
    assert api_client.get(f"/api/v1/organisations/{uuid.uuid4()}/board-members/{mid}").status_code == 404


def test_invited_participants_link_by_email(api_client, db_session, org) -> None:
    ev = _evaluation(db_session, org, "eval-invite-link")
    m = _member(db_session, org)
    db_session.commit()
    res = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/invite", json={"send_email": False, "participants": [
        {"email": " MEMBER07@demo.test ", "full_name": "Board Member 07", "role": "NED"},
        {"email": "outsider@demo.test", "full_name": "Outside Person", "role": "NED"},
    ]})
    assert res.status_code in (200, 201), res.text
    rows = {p.full_name: p for p in db_session.execute(
        select(Participant).where(Participant.evaluation_id == ev.id)).scalars()}
    assert rows["Board Member 07"].board_member_id == m.id
    assert rows["Outside Person"].board_member_id is None


def test_profiles_carry_over_to_next_years_evaluation(api_client, db_session, org) -> None:
    m = _ready_member(db_session, org)
    version = m.profile_version
    first = _evaluation(db_session, org, "eval-carry-2025")
    db_session.commit()
    api_client.post(f"/api/v1/evaluations/{first.id}/participants/from-board-members")
    second = _evaluation(db_session, org, "eval-carry-2026")
    db_session.commit()
    assert api_client.post(f"/api/v1/evaluations/{second.id}/participants/from-board-members").json()["created"] == 1

    for ev in (first, second):
        [item] = api_client.get(f"/api/v1/evaluations/{ev.id}/readiness").json()["items"]
        assert (item["board_member_id"], item["status"], item["profile_version"]) == (str(m.id), "ready", version)
    assert db_session.execute(select(BoardMember).where(BoardMember.organisation_id == org.id)).scalars().all() == [m]

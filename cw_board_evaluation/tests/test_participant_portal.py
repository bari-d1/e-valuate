"""
The participant portal for assembled question sets on a VAL-001-style evaluation:
one assignment and one link per participant, the invite email, the hub, loading
(and locking), saving answers, submitting, confirm-item corrections and friendly
errors. Placeholder names and emails only; email sending is faked.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.db.models import (
    AssessmentAssignment,
    BoardMemberFact,
    Evaluation,
    OrganisationFact,
    Question,
    QuestionBankItem,
    Response,
)
from app.services import participant_portal as form
from app.services import question_assembly as qa
from app.services import question_review as qr
from app.services import question_sets as qs
from app.services.email_service import RESERVED_SKIP_MESSAGE, form_invite_content, send_form_invite_email
from app.services.question_bank import load_fixture
from tests.val001 import build_val001

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"
BY = "Consultant A"

# What a question in the form may carry: nothing internal (codes, tags, rule reasons, AI wording)
QUESTION_KEYS = {"kind", "id", "text", "answer_type", "options", "scale", "required", "about", "follows", "confirm"}
GRID_KEYS = {"kind", "id", "statements", "colleagues", "scale", "required"}


@pytest.fixture
def val001(db_session, reference_seeded, monkeypatch):
    monkeypatch.delenv("AI_TAILORING_ENABLED", raising=False)
    monkeypatch.delenv("ASSEMBLY_COVERAGE_FLOOR", raising=False)
    summary = load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert not summary["errors"]
    db_session.execute(update(QuestionBankItem).values(status="approved"))
    db_session.flush()
    ev, parts, committees = build_val001(db_session)
    qa.run_assembly(db_session, qa.create_run(db_session, ev))
    for p in parts.values():
        p.email = p.email.lower()  # invite looks emails up in lower case
    db_session.flush()
    return ev, parts, committees


@pytest.fixture
def mailer(monkeypatch):
    """Fake the form email; returns the list of calls (keyword arguments)."""
    import app.services.email_service as email_service

    sent = []
    monkeypatch.setattr(email_service, "send_form_invite_email", lambda **kw: (sent.append(kw) or True, None))
    return sent


def _approve(db, p):
    qs.approve_set(db, qs.question_set(db, p.id), BY, override_reason="Scope agreed with the client")
    db.flush()


def _invite(api_client, ev, p):
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/invite",
                        json={"participants": [{"email": p.email}], "send_email": True})
    assert r.status_code == 201, r.text
    return r.json()["existing_items"][0]


def _assignment(db, p):
    rows = db.execute(select(AssessmentAssignment).where(AssessmentAssignment.respondent_participant_id == p.id)
                      ).scalars().all()
    assert len(rows) == 1
    return rows[0]


def _ready(api_client, db, ev, p):
    """Approve and invite one participant; their form token."""
    _approve(db, p)
    _invite(api_client, ev, p)
    return _assignment(db, p).access_token


def _questions(data):
    """Every answerable question in a loaded form, with grid cells as rating questions."""
    out = []
    for s in data["sections"]:
        for b in s["blocks"]:
            if b["kind"] == "grid":
                for st in b["statements"]:
                    for qid in st["cells"].values():
                        out.append({"id": qid, "answer_type": "rating", "scale": b["scale"], "required": b["required"],
                                    "follows": None, "confirm": None, "section": s["key"]})
            else:
                out.append({**b, "section": s["key"]})
    return out


def _value(q, yes_no="no"):
    if q["confirm"]:
        return {"status": "correct"}
    return {"rating": 4, "yesno": yes_no, "comment": None,
            "single_select": (q.get("options") or [None])[0],
            "multi_select": (q.get("options") or [])[:1]}[q["answer_type"]]


def _answer_all(api_client, token, data, yes_no="no"):
    answers = [{"question_id": q["id"], "value": _value(q, yes_no)} for q in _questions(data)
               if q["answer_type"] != "comment" or q["confirm"]]
    r = api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": answers})
    assert r.status_code == 200, r.text
    return r.json()


# ----------------------------
# Assignments, tokens and invites
# ----------------------------

def test_approving_and_inviting_creates_one_assignment_and_reinviting_reuses_it(api_client, db_session, val001,
                                                                              mailer) -> None:
    ev, parts, _ = val001
    p4 = parts["P004"]
    item = _invite(api_client, ev, p4)  # not approved: blocked, nothing created
    assert item["invite_blocked"] and not db_session.execute(select(AssessmentAssignment)).scalars().all()

    _approve(db_session, p4)
    item = _invite(api_client, ev, p4)
    a = _assignment(db_session, p4)
    assert a.assignment_type == "ASSEMBLED" and a.question_set_id == qs.question_set(db_session, p4.id).id
    assert len(a.access_token) >= 43 and a.email_sent_at is not None  # 32 random bytes, URL-safe
    assert item["email_sent"] is True and item["assignment_portal_urls"] == [form.form_link(a)]
    assert "/form/" in item["assignment_portal_urls"][0]

    first = a.access_token
    _invite(api_client, ev, p4)
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/notify-links", json={"include_hub_only": True})
    assert r.json()["email_sent"] == 1 and len(r.json()["blocked_not_approved"]) == 6
    assert _assignment(db_session, p4).access_token == first  # reused, same link
    assert [m["form_url"] for m in mailer] == [form.form_link(a)] * 3


def test_legacy_generate_assignments_refuses_assembled_evaluations(api_client, db_session, val001) -> None:
    ev, _, _ = val001
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/tracks/generate-assignments", json={})
    assert r.status_code == 409 and "assembled question sets" in r.json()["detail"]


def test_the_invite_email_has_one_link_the_notice_and_skips_reserved_domains(db_session, val001, monkeypatch) -> None:
    ev, _, _ = val001
    ev.participant_notice = "Answers are seen only by the consultants."
    ev.deadline = date(2026, 11, 20)
    subject, plain, html = form_invite_content(
        full_name="Board Member 004", form_url="https://portal.example/form/abc", organisation="VAL-001 Test Company",
        evaluation_name="2025 Board Evaluation", consultancy="Crest & Waterfalls", estimated_minutes=40,
        deadline=ev.deadline, notice=form.participant_notice(ev))
    assert plain.count("https://") == 1 and html.count('href="') == 1
    for text in ("Crest & Waterfalls", "2025 Board Evaluation", "about 40 minutes", "20 November 2026",
                 "save as you go", "Answers are seen only by the consultants."):
        assert text in plain

    monkeypatch.setenv("EMAIL_ENABLED", "true")
    assert send_form_invite_email(to_email="P004@example.invalid", full_name=None, form_url="https://x/form/t",
                                  organisation="Co", evaluation_name="E", consultancy="C") == (False, RESERVED_SKIP_MESSAGE)


def test_the_default_notice_promises_nothing_about_anonymity(db_session, val001) -> None:
    ev, _, _ = val001
    notice = form.participant_notice(ev)
    assert notice == form.default_notice() and "anonym" not in notice.lower() and "confidential" not in notice.lower()


def test_the_hub_points_to_the_one_form(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    p4, p5 = parts["P004"], parts["P005"]
    token = _ready(api_client, db_session, ev, p4)
    hub = api_client.get(f"/api/v1/portal/hub/{p4.access_token}").json()
    assert hub["form_path"] == f"/form/{token}" and hub["assignments"] == []
    assert _invite(api_client, ev, p5)["invite_blocked"]  # gives them a hub token, but no form yet
    waiting = api_client.get(f"/api/v1/portal/hub/{p5.access_token}").json()  # not approved yet
    assert waiting["form_path"] is None and "isn't ready" in waiting["form_message"]
    # The legacy questionnaire endpoints send an assembled token to the form instead
    r = api_client.get(f"/api/v1/portal/{token}")
    assert r.status_code == 409 and r.json()["detail"]["form_path"] == f"/form/{token}"


# ----------------------------
# Loading
# ----------------------------

def test_first_open_locks_the_set_and_consultant_edits_are_refused_after(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    p4 = parts["P004"]
    token = _ready(api_client, db_session, ev, p4)
    assert qs.question_set(db_session, p4.id).status == "approved"
    r = api_client.get(f"/api/v1/portal/a/{token}")
    assert r.status_code == 200 and r.json()["status"] == "not_started"
    pset = qs.question_set(db_session, p4.id)
    a = _assignment(db_session, p4)
    assert pset.status == "locked" and a.opened_at is not None
    q = db_session.get(Question, _questions(r.json())[0]["id"])
    with pytest.raises(qa.SetConflict):
        qr.remove_question(db_session, q, BY, "Too long")
    with pytest.raises(qa.SetConflict):
        qs.reopen_set(db_session, pset, BY, "Change of plan")
    opened = a.opened_at
    api_client.get(f"/api/v1/portal/a/{token}")
    assert _assignment(db_session, p4).opened_at == opened  # only the first open is recorded


def test_the_form_has_no_internal_fields_and_the_peer_grid_is_one_block(api_client, db_session, val001,
                                                                        mailer) -> None:
    ev, parts, _ = val001
    p4 = parts["P004"]
    token = _ready(api_client, db_session, ev, p4)
    data = api_client.get(f"/api/v1/portal/a/{token}").json()
    assert set(data) == {"evaluation", "participant", "estimated_minutes", "status", "opened_at", "submitted_at",
                         "sections", "answers", "progress"}
    assert data["evaluation"]["notice"] == form.default_notice() and data["estimated_minutes"] > 0
    titles = [s["title"] for s in data["sections"]]
    assert titles[0] == "Board" and "Colleagues" in titles and "Confirm details" in titles

    blocks = [b for s in data["sections"] for b in s["blocks"]]
    grids = [b for b in blocks if b["kind"] == "grid"]
    assert len(grids) == 1
    for b in blocks:
        assert set(b) == (GRID_KEYS if b["kind"] == "grid" else QUESTION_KEYS)
    raw = json.dumps(data)
    for internal in ("PEER-CORE", "BOARD-", "theme_code", "selection_reason", "ai_text", "bank_text", "text_source",
                     "P001", "P004 ·", "@example.invalid", token):
        assert internal not in raw

    grid = grids[0]
    rows = db_session.execute(select(Question).where(Question.participant_id == p4.id,
                                                     Question.status == "locked")).scalars().all()
    codes = {i.id: i.code for i in db_session.execute(select(QuestionBankItem)).scalars()}
    cells = {str(q.id) for q in rows if codes.get(q.bank_item_id, "").startswith("PEER-CORE-")}
    assert {qid for s in grid["statements"] for qid in s["cells"].values()} == cells
    # A statement may not apply to every colleague (e.g. not to executives): those cells are simply absent
    assert len(cells) <= len(grid["statements"]) * len(grid["colleagues"])
    assert all(s["cells"] for s in grid["statements"]) and len(grid["statements"]) == 6
    names = [c["name"] for c in grid["colleagues"]]
    assert "Board Member 004" not in names and all(n.startswith("Board Member") for n in names)
    assert [p["label"] for p in grid["scale"]["points"]] == ["Poor", "Average", "Good", "Very good", "Excellent"]
    committee_qs = [b for s in data["sections"] if s["key"] == "committees" for b in s["blocks"]]
    assert committee_qs and all(b["about"] and "Committee" in b["about"] for b in committee_qs)


# ----------------------------
# Answers
# ----------------------------

def test_answers_are_validated_and_scoped_to_the_participants_own_set(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    p4, p5 = parts["P004"], parts["P005"]
    token = _ready(api_client, db_session, ev, p4)
    data = api_client.get(f"/api/v1/portal/a/{token}").json()
    qs4 = _questions(data)
    rating = next(q for q in qs4 if q["answer_type"] == "rating")
    yesno = next(q for q in qs4 if q["answer_type"] == "yesno" and not q["confirm"])
    choice = next(q for q in qs4 if q["answer_type"] == "single_select")
    other = db_session.execute(select(Question).where(Question.participant_id == p5.id)).scalars().first()

    def put(qid, value):
        return api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{"question_id": qid, "value": value}]})

    for qid, bad in ((rating["id"], 6), (rating["id"], "4"), (yesno["id"], "maybe"), (choice["id"], "Something else"),
                     (str(other.id), 3)):
        r = put(qid, bad)
        assert r.status_code == 422 and r.json()["detail"]["errors"][0]["question_id"] == qid
    assert put(str(other.id), 3).json()["detail"]["errors"][0]["message"] == "This question isn't part of your form."
    assert not db_session.execute(select(Response)).scalars().all()  # nothing saved from a rejected batch

    for _ in range(2):  # idempotent upsert
        assert put(rating["id"], 2).status_code == 200
    assert put(rating["id"], 5).status_code == 200
    [r] = db_session.execute(select(Response).where(Response.question_id == rating["id"])).scalars().all()
    q = db_session.get(Question, rating["id"])
    assert r.score == 5 and r.answer == {"value": 5} and r.evaluation_subject_id == q.evaluation_subject_id
    assert put(yesno["id"], "yes").status_code == 200
    assert db_session.execute(select(Response.score).where(Response.question_id == yesno["id"])).scalar_one() == 1
    assert _assignment(db_session, p4).last_activity_at is not None

    assert put(rating["id"], None).status_code == 200  # clearing removes the answer
    assert not db_session.execute(select(Response).where(Response.question_id == rating["id"])).scalars().all()
    loaded = api_client.get(f"/api/v1/portal/a/{token}").json()
    assert loaded["answers"][yesno["id"]] == "yes" and loaded["status"] == "in_progress"


# ----------------------------
# Submission
# ----------------------------

def test_submit_lists_what_is_missing_counts_follow_ups_only_when_shown_and_is_final(api_client, db_session, val001,
                                                                                   mailer) -> None:
    ev, parts, _ = val001
    p7 = parts["P007"]  # the company secretary's set has "If so..." follow-ups
    token = _ready(api_client, db_session, ev, p7)
    data = api_client.get(f"/api/v1/portal/a/{token}").json()
    r = api_client.post(f"/api/v1/portal/a/{token}/submit")
    assert r.status_code == 422 and r.json()["detail"]["missing"]
    assert set(r.json()["detail"]["missing"][0]) == {"question_id", "section", "text", "about"}

    questions = _questions(data)
    follow = next(q for q in questions if q["follows"] and q["answer_type"] == "single_select")
    # Every follow-up in the bank is optional today: make this one required to test the rule
    item = db_session.get(QuestionBankItem, db_session.get(Question, follow["id"]).bank_item_id)
    item.priority = "standard"
    db_session.flush()
    _answer_all(api_client, token, data, yes_no="no")
    api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{"question_id": follow["id"], "value": None}]})
    # The parent is "no": the follow-up isn't shown, so it isn't missing
    parent = follow["follows"]["question_id"]
    a = _assignment(db_session, p7)
    assert not form.missing_required(db_session, a, p7)
    api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{"question_id": parent, "value": "yes"}]})
    missing = form.missing_required(db_session, a, p7)
    assert [m["question_id"] for m in missing] == [follow["id"]]
    r = api_client.post(f"/api/v1/portal/a/{token}/submit")
    assert r.status_code == 422 and [m["question_id"] for m in r.json()["detail"]["missing"]] == [follow["id"]]
    # Answered while shown, then hidden again: the hidden answer isn't kept on submission
    api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [
        {"question_id": follow["id"], "value": follow["options"][0]}, {"question_id": parent, "value": "no"}]})

    r = api_client.post(f"/api/v1/portal/a/{token}/submit")
    assert r.status_code == 200 and r.json()["submitted"] is True
    assert not db_session.execute(select(Response).where(Response.question_id == follow["id"])).scalars().all()
    a = _assignment(db_session, p7)
    assert a.submitted_at and a.status == "responded" and p7.status == "responded"
    r = api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{"question_id": parent, "value": "yes"}]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "submitted"
    assert api_client.post(f"/api/v1/portal/a/{token}/submit").status_code == 409
    after = api_client.get(f"/api/v1/portal/a/{token}").json()  # still readable, as a summary
    assert after["status"] == "submitted" and after["answers"][parent] == "no"


def test_a_confirm_correction_becomes_a_participant_proposal_and_never_changes_the_fact(api_client, db_session, val001,
                                                                                       mailer) -> None:
    ev, parts, _ = val001
    p4 = parts["P004"]
    token = _ready(api_client, db_session, ev, p4)
    data = api_client.get(f"/api/v1/portal/a/{token}").json()
    confirms = [q for q in _questions(data) if q["confirm"]]
    assert confirms and all(q["confirm"]["value"] for q in confirms)
    expertise = next(q for q in confirms if q["confirm"]["label"] == "Expertise")
    assert expertise["confirm"]["value"] == "Finance"
    _answer_all(api_client, token, data)
    api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{
        "question_id": expertise["id"], "value": {"status": "needs_updating", "correction": "Finance and actuarial science"}}]})
    assert api_client.post(f"/api/v1/portal/a/{token}/submit").json()["proposals"] == 1

    facts = db_session.execute(select(BoardMemberFact).where(BoardMemberFact.board_member_id == p4.board_member_id,
                                                             BoardMemberFact.key == "expertise")).scalars().all()
    confirmed = [f for f in facts if f.status == "confirmed"]
    [proposal] = [f for f in facts if f.status == "proposed"]
    assert confirmed[0].value == ["Finance"]  # unchanged
    assert proposal.origin == "participant" and proposal.value == "Finance and actuarial science"
    assert "Board Member 004" in proposal.note and "needs updating" in proposal.note

    member = api_client.get(f"/api/v1/organisations/{ev.organisation_id}/board-members/{p4.board_member_id}/facts")
    assert member.status_code == 200  # the profile page lists it with its origin
    assert [f["value"] for f in member.json()["items"] if f["origin"] == "participant"] == ["Finance and actuarial science"]


def test_corrections_to_company_facts_go_to_the_organisation_and_can_sit_beside_other_proposals(db_session, val001) -> None:
    ev, parts, _ = val001
    p7 = parts["P007"]
    q = next((q for q in db_session.execute(select(Question).where(Question.participant_id == p7.id,
                                                                   Question.section == "confirm")).scalars()
              if (q.confirm_value or {}).get("known_from") == "board_size"), None)
    if q is None:
        pytest.skip("No board size confirm item for the company secretary in this bank")
    db_session.add(OrganisationFact(organisation_id=ev.organisation_id, key="board_size", value=7, source="public",
                                    status="proposed", origin="ai_extraction"))
    for p in (p7, parts["P001"]):
        form.propose_correction(db_session, ev, p, q, "Eight since July")
    rows = db_session.execute(select(OrganisationFact).where(OrganisationFact.organisation_id == ev.organisation_id,
                                                             OrganisationFact.key == "board_size")).scalars().all()
    assert sorted(f.origin for f in rows if f.status == "proposed") == ["ai_extraction", "participant", "participant"]
    assert [f.value for f in rows if f.status == "confirmed"] == [6]


# ----------------------------
# Friendly errors
# ----------------------------

def test_unknown_expired_closed_and_reopened_links_get_friendly_errors(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    p4, p5 = parts["P004"], parts["P005"]
    r = api_client.get("/api/v1/portal/a/not-a-real-token")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "invalid_link"
    r = api_client.get(f"/api/v1/portal/a/{p4.access_token}")  # a hub token isn't a form link
    assert r.status_code == 404

    token = _ready(api_client, db_session, ev, p4)
    ev.deadline = date.today() - timedelta(days=1)
    db_session.flush()
    r = api_client.get(f"/api/v1/portal/a/{token}")
    assert r.status_code == 410 and r.json()["detail"]["code"] == "expired" and "deadline" in r.json()["detail"]["message"]
    ev.deadline, ev.status = None, "closed"
    db_session.flush()
    r = api_client.get(f"/api/v1/portal/a/{token}")
    assert r.status_code == 410 and r.json()["detail"]["code"] == "closed"
    ev.status = "live"
    db_session.flush()

    token5 = _ready(api_client, db_session, ev, p5)
    qs.reopen_set(db_session, qs.question_set(db_session, p5.id), BY, "One more committee question")
    db_session.flush()
    r = api_client.get(f"/api/v1/portal/a/{token5}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "being_updated"
    for detail in (api_client.get("/api/v1/portal/a/x").json()["detail"], r.json()["detail"]):
        assert set(detail) == {"code", "message"}


# ----------------------------
# End to end
# ----------------------------

def test_every_val001_participant_can_load_answer_and_submit(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    for p in parts.values():
        _approve(db_session, p)
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/notify-links", json={"include_hub_only": True})
    assert r.json()["email_sent"] == 7 and len(mailer) == 7
    assert len(db_session.execute(select(AssessmentAssignment)).scalars().all()) == 7
    for code, p in parts.items():
        token = _assignment(db_session, p).access_token
        data = api_client.get(f"/api/v1/portal/a/{token}").json()
        assert data["sections"], code
        saved = _answer_all(api_client, token, data)
        assert saved["progress"]["required_answered"] == saved["progress"]["required"], code
        r = api_client.post(f"/api/v1/portal/a/{token}/submit")
        assert r.status_code == 200, (code, r.text)
    n = db_session.execute(select(Response).where(Response.evaluation_id == ev.id)).scalars().all()
    assert n and all(r.evaluation_subject_id for r in n)
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/notify-links",
                        json={"include_hub_only": True, "only_pending": True})
    assert r.json()["email_sent"] == 0 and {s["reason"] for s in r.json()["skipped_no_links"]} == {"already_submitted"}
    assert db_session.get(Evaluation, ev.id).status  # untouched

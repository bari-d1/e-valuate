"""
Consultant review of assembled sets on a VAL-001-style evaluation: tag edits,
remove and restore, adding from the bank or by hand, reordering, reopening,
bulk approval, the audit trail, live metrics, the cross-participant views and
the invite gate. AI is off; suggestions are set directly where needed.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.db.models import (
    Evaluation,
    EvaluationSubject,
    Participant,
    Question,
    QuestionBankItem,
    QuestionSetEvent,
    QuestionSubjectType,
)
from app.services import question_assembly as qa
from app.services import question_review as qr
from app.services import question_sets as qs
from app.services.question_bank import load_fixture
from tests.val001 import build_val001

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"
BY = "Consultant A"


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
    return ev, parts, committees


def _qs(db, p, *, active=False):
    rows = db.execute(select(Question).where(Question.participant_id == p.id).order_by(Question.sort_order)).scalars().all()
    return qa.active_questions(list(rows)) if active else list(rows)


def _code(db, q):
    return db.get(QuestionBankItem, q.bank_item_id).code if q.bank_item_id else None


def _events(db, p, action=None):
    stmt = select(QuestionSetEvent).where(QuestionSetEvent.participant_id == p.id)
    if action:
        stmt = stmt.where(QuestionSetEvent.action == action)
    return db.execute(stmt.order_by(QuestionSetEvent.created_at)).scalars().all()


def _subject(db, ev, label_part):
    return next(s for s in db.execute(select(EvaluationSubject).where(EvaluationSubject.evaluation_id == ev.id)).scalars()
                if label_part in s.label)


def _metrics(db, p):
    return qa.set_metrics(db, qs.question_set(db, p.id))


# ----------------------------
# Tags
# ----------------------------

def test_tags_change_but_a_question_always_keeps_a_subject(db_session, val001) -> None:
    ev, parts, _ = val001
    p6 = parts["P006"]
    q = next(q for q in _qs(db_session, p6) if q.section == "board")
    qr.edit_tags(db_session, ev, q, BY, {"theme_code": "RISK_MONITORING" if q.theme_code != "RISK_MONITORING" else "STRATEGY"})
    assert q.dimension and q.theme_code in ("RISK_MONITORING", "STRATEGY")
    [event] = _events(db_session, p6, "edit_tags")
    assert event.created_by == BY and event.created_at and event.detail["before"]["theme_code"] != event.detail["after"]["theme_code"]

    with pytest.raises(ValueError, match="must keep a subject"):
        qr.edit_tags(db_session, ev, q, BY, {"subject_id": None})
    with pytest.raises(ValueError, match="theme and an evidence source"):
        qr.edit_tags(db_session, ev, q, BY, {"theme_code": ""})
    # A bank question about the board can't be pointed at a committee
    committee = _subject(db_session, ev, "Audit")
    with pytest.raises(ValueError, match="doesn't fit"):
        qr.edit_tags(db_session, ev, q, BY, {"subject_id": str(committee.id)})
    assert q.evaluation_subject_id and q.subject_type_codes == ["BOARD"]


def test_written_questions_need_tags_and_an_answer_type_and_can_change_subject(db_session, val001) -> None:
    ev, parts, _ = val001
    p6 = parts["P006"]
    board = _subject(db_session, ev, "The board")
    with pytest.raises(ValueError, match="an answer type, a theme"):
        qr.add_written(db_session, ev, p6, BY, text="How well does the board use its away days?", answer_type="",
                       subject_id=str(board.id), theme_code=None, evidence_source_code="PERCEPTION")
    with pytest.raises(ValueError, match="at least two options"):
        qr.add_written(db_session, ev, p6, BY, text="Which?", answer_type="single_select", subject_id=str(board.id),
                       theme_code="STRATEGY", evidence_source_code="PERCEPTION", options=["Only one"])
    q = qr.add_written(db_session, ev, p6, BY, text="How well does the board use its away days?", answer_type="rating",
                       subject_id=str(board.id), theme_code="STRATEGY", evidence_source_code="PERCEPTION")
    assert (q.text_source, q.section, q.added_by, q.subject_type_codes) == ("consultant_written", "board", BY, ["BOARD"])
    assert q.scale and q.bank_item_id is None
    # Written questions may be about any subject; the section follows it
    committee = _subject(db_session, ev, "Audit")
    qr.edit_tags(db_session, ev, q, BY, {"subject_id": str(committee.id)})
    assert (q.section, q.subject_type_codes) == ("committees", ["COMMITTEE"])
    assert [e.action for e in _events(db_session, p6)] == ["add_written", "edit_tags"]


# ----------------------------
# Remove, restore, add, move
# ----------------------------

def test_removed_questions_leave_counts_coverage_and_the_set_and_restore_brings_them_back(db_session, val001) -> None:
    ev, parts, _ = val001
    p6 = parts["P006"]
    before = _metrics(db_session, p6)
    q = next(q for q in _qs(db_session, p6) if q.section == "committees")
    subject_id = str(q.evaluation_subject_id)
    covered_before = next(c for c in before["coverage"] if c["subject_id"] == subject_id)["questions"]

    qr.remove_question(db_session, q, BY, "Covered in the interview")
    after = _metrics(db_session, p6)
    assert q.status == "removed" and q.removed_reason == "Covered in the interview"
    assert after["counts"]["questions"] == before["counts"]["questions"] - 1 and after["counts"]["removed"] == 1
    assert next(c for c in after["coverage"] if c["subject_id"] == subject_id)["questions"] == covered_before - 1
    assert after["estimated_minutes"] <= before["estimated_minutes"]
    with pytest.raises(qa.SetConflict, match="restore it first"):
        qs.choose_wording(db_session, q, "edited", BY, "Changed")

    qr.restore_question(db_session, q, BY)
    assert q.status == "draft" and _metrics(db_session, p6)["counts"] == before["counts"]

    # Approval leaves removed questions out of what the participant gets
    qr.remove_question(db_session, q, BY)
    pset = qs.question_set(db_session, p6.id)
    qs.approve_set(db_session, pset, BY, override_reason="Test")
    assert q.status == "removed"
    assert {r.status for r in _qs(db_session, p6) if r.id != q.id} <= {"approved"}
    assert [e.action for e in _events(db_session, p6)] == ["remove", "restore", "remove", "approve"]


def test_removing_a_question_takes_its_follow_ups_with_it(db_session, val001) -> None:
    ev, parts, _ = val001
    p, child = next((p, q) for p in parts.values() for q in _qs(db_session, p) if q.depends_on_question_id)
    parent = db_session.get(Question, child.depends_on_question_id)
    qr.remove_question(db_session, parent, BY)
    assert child.status == "removed" and child.removed_reason == qr.FOLLOWS_REMOVED
    with pytest.raises(qa.SetConflict, match="restore that one first"):
        qr.restore_question(db_session, child, BY)
    qr.restore_question(db_session, parent, BY)
    assert child.status == "draft"


def test_adding_from_the_bank_fills_placeholders_like_assembly(db_session, val001) -> None:
    ev, parts, _ = val001
    # A templated item someone got, added by hand for someone who didn't get it about that subject
    templated = []
    for code, p in parts.items():
        for q in _qs(db_session, p):
            item = db_session.get(QuestionBankItem, q.bank_item_id) if q.bank_item_id else None
            if item and item.placeholders and not any(k.startswith("respondent.") for k in item.placeholders):
                templated.append((p, q, item))
    assert templated
    for source_p, source_q, item in templated:
        target = next((p for p in parts.values() if p.id != source_p.id and not any(
            q.bank_item_id == item.id and q.evaluation_subject_id == source_q.evaluation_subject_id
            for q in _qs(db_session, p))), None)
        if target is not None:
            break
    q = qr.add_from_bank(db_session, ev, target, str(item.id), str(source_q.evaluation_subject_id), BY)
    assert q.text == source_q.bank_text and "{" not in q.text
    assert (q.text_source, q.added_by, q.bank_item_version) == ("bank", BY, item.version)
    assert q.theme_code == item.theme_code and q.evidence_source_code == item.evidence_source_code
    assert q.subject_type_codes == [db_session.get(EvaluationSubject, q.evaluation_subject_id).subject_type_code]
    rows = _qs(db_session, target)
    assert [r.sort_order for r in rows] == sorted(r.sort_order for r in rows)
    assert [r.section for r in rows] == sorted((r.section for r in rows), key=qa.SECTIONS.index)
    with pytest.raises(qa.SetConflict, match="already in this set"):
        qr.add_from_bank(db_session, ev, target, str(item.id), str(source_q.evaluation_subject_id), BY)
    [event] = _events(db_session, target, "add_from_bank")
    assert event.detail["code"] == item.code and event.created_by == BY

    # Re-assembly keeps what the consultant added
    qa.run_assembly(db_session, qa.create_run(db_session, ev, participant_ids=[str(target.id)]))
    assert any(r.id == q.id for r in _qs(db_session, target))


def test_adding_needs_an_approved_item_of_the_right_subject_type(db_session, val001) -> None:
    ev, parts, _ = val001
    p1 = parts["P001"]
    item = db_session.execute(select(QuestionBankItem).where(QuestionBankItem.code == "BOARD-RISK-02")).scalars().first()
    committee = _subject(db_session, ev, "Audit")
    with pytest.raises(ValueError, match="doesn't fit"):
        qr.add_from_bank(db_session, ev, p1, str(item.id), str(committee.id), BY)
    item.status = "draft"
    with pytest.raises(ValueError, match="only approved"):
        qr.add_from_bank(db_session, ev, p1, str(item.id), str(_subject(db_session, ev, "The board").id), BY)


def test_reorder_within_a_section(db_session, val001) -> None:
    ev, parts, _ = val001
    p6 = parts["P006"]
    board = [q for q in _qs(db_session, p6) if q.section == "board"]
    first, second = board[0], board[1]
    qr.move_question(db_session, second, BY, direction="up")
    board = [q for q in _qs(db_session, p6) if q.section == "board"]
    assert board[0].id == second.id and board[1].id == first.id
    qr.move_question(db_session, second, BY, position=3)
    assert [q.id for q in _qs(db_session, p6) if q.section == "board"][2] == second.id
    qr.move_question(db_session, second, BY, direction="up")
    rows = _qs(db_session, p6)
    assert [r.section for r in rows] == sorted((r.section for r in rows), key=qa.SECTIONS.index)
    assert [e.detail["after"] for e in _events(db_session, p6, "move")] == [1, 3, 2]


# ----------------------------
# Lifecycle
# ----------------------------

def test_every_action_is_refused_on_approved_and_locked_sets_and_reopen_only_before_locking(db_session, val001) -> None:
    ev, parts, _ = val001
    p6 = parts["P006"]
    pset = qs.question_set(db_session, p6.id)
    q = next(q for q in _qs(db_session, p6) if q.section == "board")
    board = _subject(db_session, ev, "The board")
    item = db_session.get(QuestionBankItem, q.bank_item_id)
    actions = [
        lambda: qr.edit_tags(db_session, ev, q, BY, {"theme_code": "STRATEGY"}),
        lambda: qr.remove_question(db_session, q, BY),
        lambda: qr.move_question(db_session, q, BY, direction="down"),
        lambda: qr.add_from_bank(db_session, ev, p6, str(item.id), str(board.id), BY),
        lambda: qr.add_written(db_session, ev, p6, BY, text="X?", answer_type="yesno", subject_id=str(board.id),
                               theme_code="STRATEGY", evidence_source_code="PERCEPTION"),
        lambda: qs.choose_wording(db_session, q, "edited", BY, "Late edit"),
    ]
    with pytest.raises(qa.SetConflict, match="still a draft"):
        qs.reopen_set(db_session, pset, BY, "Too early")
    qs.approve_set(db_session, pset, BY, override_reason="Test")
    for act in actions:
        with pytest.raises(qa.SetConflict, match="approved; reopen it"):
            act()
    with pytest.raises(ValueError, match="reason"):
        qs.reopen_set(db_session, pset, BY, " ")
    qs.reopen_set(db_session, pset, BY, "Client asked for one more question")
    assert pset.status == "draft" and pset.approved_by is None
    assert {r.status for r in _qs(db_session, p6)} == {"draft"}
    qr.edit_tags(db_session, ev, q, BY, {"theme_code": "STRATEGY"})  # editable again

    qs.approve_set(db_session, pset, BY, override_reason="Test")
    qs.lock_set(db_session, pset)
    for act in actions:
        with pytest.raises(qa.SetConflict, match="locked"):
            act()
    with pytest.raises(qa.SetConflict, match="can't be reopened"):
        qs.reopen_set(db_session, pset, BY, "Too late")
    events = _events(db_session, p6)
    assert [e.action for e in events] == ["approve", "reopen", "edit_tags", "approve", "lock"]
    assert events[1].detail["reason"] == "Client asked for one more question" and events[1].created_by == BY
    assert all(e.created_at for e in events)


def test_bulk_approve_returns_per_participant_results_and_stores_the_override(db_session, val001, monkeypatch) -> None:
    ev, parts, _ = val001
    ids = [str(p.id) for p in parts.values()]
    outsider = Participant(evaluation_id=ev.id, email="new@example.invalid", full_name="Not Assembled", status="invited")
    db_session.add(outsider)
    db_session.flush()
    monkeypatch.setenv("ASSEMBLY_COVERAGE_FLOOR", "1000")  # every set has gaps now
    results = qr.bulk_approve(db_session, ev, ids + [str(outsider.id)], BY)
    assert {r["outcome"] for r in results[:7]} == {"not_approved"}
    assert all("coverage gap" in r["reason"] for r in results[:7])
    assert results[7] == {"participant_id": str(outsider.id), "label": "Not Assembled", "outcome": "not_approved",
                          "reason": "No question set has been assembled for them yet."}

    results = qr.bulk_approve(db_session, ev, ids, BY, override_reason="Agreed scope with the client")
    assert [r["outcome"] for r in results] == ["approved"] * 7
    for p in parts.values():
        pset = qs.question_set(db_session, p.id)
        assert pset.status == "approved" and pset.override_reason == "Agreed scope with the client"
        [event] = _events(db_session, p, "approve")
        assert event.detail["batch"] is True and event.detail["override_reason"] == "Agreed scope with the client"
    again = qr.bulk_approve(db_session, ev, ids[:1], BY)
    assert again[0]["outcome"] == "not_approved" and "already approved" in again[0]["reason"]


# ----------------------------
# Cross-participant views
# ----------------------------

def test_by_subject_groups_the_chairs_questions_across_participants(db_session, val001) -> None:
    ev, parts, _ = val001
    chair = _subject(db_session, ev, "P001")
    view = qr.by_subject(db_session, ev, str(chair.id))
    assert view["subject"]["type"] == "CHAIR" and view["questions"] > 0
    expected = {str(q.participant_id) for p in parts.values() for q in _qs(db_session, p, active=True)
                if q.evaluation_subject_id == chair.id} - {str(parts["P001"].id)}
    assert view["rater_count"] == len(expected) and view["too_few_raters"] == (len(expected) < 3)
    codes = [g["code"] for g in view["groups"]]
    assert len(codes) == len(set(codes))  # one group per bank item
    for g in view["groups"]:
        rows = [q for p in parts.values() for q in _qs(db_session, p, active=True)
                if q.evaluation_subject_id == chair.id and _code(db_session, q) == g["code"]]
        assert sorted(e["question_id"] for e in g["entries"]) == sorted(str(q.id) for q in rows)

    # One participant's wording rewritten: the group is flagged as worded differently
    g = next(g for g in view["groups"] if len(g["entries"]) > 1)
    q = db_session.get(Question, __import__("uuid").UUID(g["entries"][0]["question_id"]))
    qs.choose_wording(db_session, q, "edited", BY, "Tell us about something else entirely, in your own words")
    regrouped = next(x for x in qr.by_subject(db_session, ev, str(chair.id))["groups"] if x["code"] == g["code"])
    assert regrouped["wordings"] == 2 and regrouped["worded_differently"] is True

    subjects = {s["id"]: s for s in qr.subjects_overview(db_session, ev)}
    assert subjects[str(chair.id)]["rater_count"] == view["rater_count"]
    ed = _subject(db_session, ev, "P003")
    assert subjects[str(ed.id)]["too_few_raters"] is (subjects[str(ed.id)]["rater_count"] < 3)


def test_overview_lists_every_participant_with_live_numbers(db_session, val001) -> None:
    ev, parts, _ = val001
    out = qr.overview(db_session, ev)
    rows = {r["display_code"]: r for r in out["participants"]}
    assert set(rows) == set(parts)
    assert {r["status"] for r in rows.values()} == {"draft"}
    assert rows["P004"]["estimated_minutes"] == 54 and rows["P004"]["long"] is True
    assert rows["P007"]["long"] is False
    assert rows["P001"]["role_label"] == "Chair" and rows["P006"]["committees"]
    assert any("ED deep set" in w for w in rows["P001"]["rater_warnings"])


# ----------------------------
# API
# ----------------------------

def test_api_edits_return_fresh_metrics(api_client, db_session, val001) -> None:
    ev, parts, _ = val001
    p6 = str(parts["P006"].id)
    h = {"X-Consultant-Name": "Tester"}
    body = api_client.get(f"/api/v1/evaluations/{ev.id}/participants/{p6}/question-set/review").json()
    assert body["header"]["role_label"] == "Independent NED" and body["subject_options"][0]["label"] == "The board"
    total = body["set"]["counts"]["questions"]
    q = body["sections"][0]["questions"][0]
    assert q["selection_reason"].startswith("Included:")

    r = api_client.post(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}/remove", json={"reason": "Dup"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "removed"
    assert r.json()["metrics"]["counts"]["questions"] == total - 1 and "rater_warnings" in r.json()["metrics"]
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}/restore", headers=h)
    assert r.json()["metrics"]["counts"]["questions"] == total
    r = api_client.patch(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}/tags", json={"subject_id": None}, headers=h)
    assert r.status_code == 400
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}/move", json={"direction": "down"}, headers=h)
    assert r.status_code == 200 and r.json()["metrics"]["estimated_minutes"] == body["set"]["estimated_minutes"]

    board = body["subject_options"][0]["id"]
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/{p6}/question-set/questions", headers=h, json={
        "source": "written", "text": "Is the board's calendar fit for purpose?", "answer_type": "yesno",
        "subject_id": board, "theme_code": "STRATEGY", "evidence_source_code": "PERCEPTION"})
    assert r.status_code == 201 and r.json()["metrics"]["counts"]["questions"] == total + 1
    found = api_client.get(f"/api/v1/evaluations/{ev.id}/review/bank-items", params={"text": "risk"}).json()["items"]
    assert found and all("risk" in (i["code"] + i["text"]).lower() for i in found)

    r = api_client.post(f"/api/v1/evaluations/{ev.id}/question-sets/approve", headers=h,
                        json={"participant_ids": [p6, str(parts["P001"].id)]})
    assert r.status_code == 200 and r.json()["approved"] == 2
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/{p6}/question-set/reopen", json={"reason": ""}, headers=h)
    assert r.status_code == 400
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/{p6}/question-set/reopen",
                        json={"reason": "One more change"}, headers=h)
    assert r.status_code == 200 and r.json()["set"]["status"] == "draft"
    history = api_client.get(f"/api/v1/evaluations/{ev.id}/participants/{p6}/question-set/review").json()["history"]
    assert [e["action"] for e in history][:3] == ["reopen", "approve", "add_written"] and history[0]["by"] == "Tester"

    overview = api_client.get(f"/api/v1/evaluations/{ev.id}/review").json()
    assert len(overview["participants"]) == 7
    subjects = api_client.get(f"/api/v1/evaluations/{ev.id}/review/subjects").json()["items"]
    chair = next(s for s in subjects if s["type"] == "CHAIR")
    view = api_client.get(f"/api/v1/evaluations/{ev.id}/review/subjects/{chair['id']}").json()
    assert view["subject"]["id"] == chair["id"] and view["groups"]


# ----------------------------
# Invite gate
# ----------------------------

def test_invites_and_links_wait_for_an_approved_set(api_client, db_session, val001, monkeypatch) -> None:
    import app.api.evaluations as evaluations_api
    import app.services.participant_notify as notify

    sent = []
    fake = lambda **kw: (sent.append(kw["to_email"]) or True, None)  # noqa: E731
    monkeypatch.setattr(evaluations_api, "send_invite_email", fake)
    monkeypatch.setattr(notify, "send_invite_email", fake)
    ev, parts, _ = val001
    p6 = parts["P006"]
    p6.email = p6.email.lower()  # invite looks emails up in lower case
    db_session.flush()

    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/invite",
                        json={"participants": [{"email": p6.email}], "send_email": True})
    [item] = r.json()["existing_items"]
    assert item["email_sent"] is False and item["invite_blocked"] == "Their question set isn't approved yet."
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/notify-links", json={"include_hub_only": True})
    assert r.json()["email_sent"] == 0 and len(r.json()["blocked_not_approved"]) == 7
    assert sent == []

    qs.approve_set(db_session, qs.question_set(db_session, p6.id), BY, override_reason="Test")
    db_session.flush()
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/invite",
                        json={"participants": [{"email": p6.email}], "send_email": True})
    assert r.json()["existing_items"][0]["email_sent"] is True and r.json()["existing_items"][0]["invite_blocked"] is None
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/notify-links", json={"include_hub_only": True})
    assert r.json()["email_sent"] == 1 and len(r.json()["blocked_not_approved"]) == 6
    assert sent == [p6.email, p6.email]

    # A new participant in an evaluation that uses assembled sets has no set yet
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/invite",
                        json={"participants": [{"email": "late@example.invalid"}], "send_email": True})
    assert r.json()["created_items"][0]["invite_blocked"] == "No question set has been assembled for them yet."


def test_evaluations_without_assembled_sets_invite_as_before(api_client, db_session, reference_seeded, monkeypatch) -> None:
    import app.api.evaluations as evaluations_api

    sent = []
    monkeypatch.setattr(evaluations_api, "send_invite_email", lambda **kw: (sent.append(kw["to_email"]) or True, None))
    ev = Evaluation(id="LEGACY-1", tenant_name="Legacy Co", sector="insurance", year=2025, regulators={"items": []})
    db_session.add(ev)
    db_session.flush()
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/invite",
                        json={"participants": [{"email": "a@example.invalid"}], "send_email": True})
    item = r.json()["created_items"][0]
    assert item["email_sent"] is True and item["invite_blocked"] is None and sent == ["a@example.invalid"]
    assert qs.invite_block_reasons(db_session, ev.id) == {}

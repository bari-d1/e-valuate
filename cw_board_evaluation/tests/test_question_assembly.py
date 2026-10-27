"""
Question assembly on a VAL-001-style evaluation: one draft set per ready
participant, known facts, follow-ups, re-runs, legacy questions, coverage,
raters, the set lifecycle, decisions and the bank feedback loop. AI is off
here (see test_question_tailoring.py for AI, mocked).

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    AssemblyRun,
    EvaluationContextSnapshot,
    EvaluationScopeSubjectType,
    ParticipantQuestionSet,
    Question,
    QuestionBankItem,
    QuestionSuggestionDecision,
)
from app.services import question_assembly as qa
from app.services import question_sets as qs
from app.services.question_bank import load_fixture
from tests.val001 import build_val001

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"


@pytest.fixture
def approved_bank(db_session, reference_seeded):
    summary = load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert not summary["errors"]
    db_session.execute(update(QuestionBankItem).values(status="approved"))
    db_session.flush()
    return db_session


@pytest.fixture
def val001(db_session, approved_bank, monkeypatch):
    monkeypatch.delenv("AI_TAILORING_ENABLED", raising=False)
    return build_val001(db_session)


def assemble(db, ev, **kw):
    run = qa.create_run(db, ev, **kw)
    qa.run_assembly(db, run)
    return run


def _qs(db, p):
    return db.execute(select(Question).where(Question.participant_id == p.id).order_by(Question.sort_order)).scalars().all()


def _code(db, q):
    return db.get(QuestionBankItem, q.bank_item_id).code if q.bank_item_id else None


def test_one_draft_set_per_ready_participant(db_session, val001) -> None:
    ev, parts, _ = val001
    run = assemble(db_session, ev)
    assert run.status == "done"
    assert [r["outcome"] for r in run.results] == ["assembled"] * 7
    for code, p in parts.items():
        pset = qs.question_set(db_session, p.id)
        assert pset.status == "draft" and pset.assembly_run_id == run.id, code
        rows = _qs(db_session, p)
        assert rows and all(q.template_code == f"P:{p.id}" and q.status == "draft" for q in rows)
        assert all(q.dimension and q.theme_code and q.evidence_source_code and q.subject_type_codes for q in rows)
        assert [q.sort_order for q in rows] == sorted(q.sort_order for q in rows)
        sections = [q.section for q in rows]
        assert sections == sorted(sections, key=qa.SECTIONS.index), code


def test_snapshot_is_linked_to_the_run(db_session, val001) -> None:
    ev, _, _ = val001
    run = assemble(db_session, ev)
    snap = db_session.get(EvaluationContextSnapshot, run.snapshot_id)
    assert snap is not None and snap.evaluation_id == ev.id and len(snap.participants) == 7


def test_participants_who_are_not_ready_are_skipped_with_reasons(db_session, val001) -> None:
    ev, parts, _ = val001
    from app.db.models import BoardMember

    db_session.get(BoardMember, parts["P005"].board_member_id).profile_status = "draft"
    db_session.flush()
    run = assemble(db_session, ev)
    p5 = next(r for r in run.results if r["participant_id"] == str(parts["P005"].id))
    assert p5["outcome"] == "skipped" and p5["reasons"] == ["Profile not marked reviewed."]
    assert _qs(db_session, parts["P005"]) == []
    assert qs.question_set(db_session, parts["P005"].id) is None


def test_placeholders_known_facts_and_follow_ups(db_session, val001) -> None:
    ev, parts, _ = val001
    assemble(db_session, ev)
    p1 = {_code(db_session, q): q for q in _qs(db_session, parts["P001"])}
    assert p1["BOARD-EFF-01"].text.startswith("Your board has 1 female member(s).")
    # known_from skip: left out and listed
    p6 = _qs(db_session, parts["P006"])
    codes6 = [_code(db_session, q) for q in p6]
    assert "INED-IND-01" not in codes6 and "INED-IND-05" in codes6
    summary = qs.question_set(db_session, parts["P006"].id).summary
    skipped = {s["code"]: s for s in summary["skipped_known"]}
    assert skipped["INED-IND-01"]["value"] == "No"
    assert "INED-IND-09" in skipped
    # known_from confirm: one confirm question showing the stored value
    confirm = [q for q in p6 if q.section == "confirm"]
    assert [_code(db_session, q) for q in confirm] == ["DIR-SELF-02"]
    assert confirm[0].confirm_value["value_text"] == "Finance"
    # follow-ups depend on the question they follow
    p7 = {_code(db_session, q): q for q in _qs(db_session, parts["P007"])}
    follow, parent = p7["SEC-12"], p7["SEC-11"]  # 3.5 "If so, who..." follows 3.4
    assert follow.depends_on_question_id == parent.id and follow.show_if == {"answer": "yes"}
    assert summary["counts"]["blocked"] == 0


def test_identical_text_is_fine_for_assembled_questions_but_not_for_legacy_ones(db_session, val001) -> None:
    ev, parts, _ = val001
    assemble(db_session, ev)
    same = db_session.scalar(select(func.count()).select_from(Question).where(
        Question.text == "Comes to board meetings well prepared"))
    assert same == 30  # six directors x five colleagues, across six participants' sets
    # Legacy template questions still enforce unique text per template and version
    db_session.add(Question(template_code="LEGACY", version=1, dimension="Board", text="Same text"))
    db_session.flush()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(Question(template_code="LEGACY", version=1, dimension="Board", text="Same text"))
            db_session.flush()


def test_legacy_template_questions_are_untouched(db_session, val001, api_client) -> None:
    ev, _, _ = val001
    db_session.add(Question(template_code="DEFAULT", version=1, dimension="Board", text="Legacy question"))
    db_session.flush()
    before = db_session.scalar(select(func.count()).select_from(Question).where(Question.template_code == "DEFAULT"))
    assemble(db_session, ev)
    after = db_session.scalar(select(func.count()).select_from(Question).where(Question.template_code == "DEFAULT"))
    assert before == after == 1
    legacy = db_session.execute(select(Question).where(Question.template_code == "DEFAULT")).scalar_one()
    assert legacy.participant_id is None and legacy.status is None and legacy.section is None
    r = api_client.get(f"/api/v1/evaluations/{ev.id}/questions", params={"template_code": "DEFAULT", "version": 1})
    assert [q["text"] for q in r.json()["items"]] == ["Legacy question"]
    # The legacy edit endpoint still edits legacy questions, and refuses assembled ones
    assert api_client.patch(f"/api/v1/questions/{legacy.id}", json={"text": "Legacy question v2"}).status_code == 200
    assembled = db_session.execute(select(Question).where(Question.participant_id.is_not(None)).limit(1)).scalar_one()
    assert api_client.patch(f"/api/v1/questions/{assembled.id}", json={"text": "x"}).status_code == 409


def test_rerun_keeps_edits_and_never_touches_approved_sets(db_session, val001) -> None:
    ev, parts, _ = val001
    assemble(db_session, ev)
    q = next(q for q in _qs(db_session, parts["P004"]) if _code(db_session, q) == "BOARD-STR-01")
    qs.choose_wording(db_session, q, "edited", "tester", "Edited wording for the core business item")
    p1_before = [(q.id, q.text) for q in _qs(db_session, parts["P001"])]
    qs.approve_set(db_session, qs.question_set(db_session, parts["P001"].id), "tester")

    run = assemble(db_session, ev)
    edited = next(q for q in _qs(db_session, parts["P004"]) if _code(db_session, q) == "BOARD-STR-01")
    assert edited.id == q.id and edited.text == "Edited wording for the core business item"
    assert edited.text_source == "consultant_edited"
    assert [(q.id, q.text) for q in _qs(db_session, parts["P001"])] == p1_before
    p1 = next(r for r in run.results if r["participant_id"] == str(parts["P001"].id))
    assert p1["outcome"] == "skipped" and "approved" in p1["reasons"][0]

    assemble(db_session, ev, reset=True)
    again = next(q for q in _qs(db_session, parts["P004"]) if _code(db_session, q) == "BOARD-STR-01")
    assert again.text_source == "bank" and again.text == again.bank_text


def test_scope_and_peer_mode_are_respected(db_session, val001) -> None:
    ev, parts, _ = val001
    db_session.add_all([EvaluationScopeSubjectType(evaluation_id=ev.id, subject_type_code=c)
                        for c in ("BOARD", "CHAIR", "MD_CEO", "ED", "NED", "INED", "COMPANY_SECRETARY")])
    ev.options = {"peer_mode": "full"}
    db_session.flush()
    assemble(db_session, ev)
    codes = [_code(db_session, q) for q in _qs(db_session, parts["P004"])]
    assert not [c for c in codes if c.startswith("COM-")], "committees are out of scope"
    assert "PEER-NED-01" in codes and not [c for c in codes if c.startswith(("PEER-CORE-", "DEEP-"))]


def test_drafts_need_the_dev_flag(db_session, val001, monkeypatch) -> None:
    ev, _, _ = val001
    monkeypatch.delenv("ASSEMBLY_ALLOW_DRAFTS", raising=False)
    with pytest.raises(qa.AssemblyError):
        qa.create_run(db_session, ev, include_drafts=True)
    monkeypatch.setenv("ASSEMBLY_ALLOW_DRAFTS", "true")
    assert qa.create_run(db_session, ev, include_drafts=True).include_drafts is True


def test_rater_warning_for_the_ed_deep_set(db_session, val001) -> None:
    ev, _, _ = val001
    run = assemble(db_session, ev)
    assert [(w["set"], w["subject"], w["rater_count"]) for w in run.rater_warnings] == [
        ("ED deep set", "P003 · Board Member 003", 2)]
    assert run.rater_warnings[0]["raters"] == ["P001 · Board Member 001", "P002 · Board Member 002"]


def test_time_counts_the_core_grid_as_one_fast_block(db_session, val001) -> None:
    ev, parts, _ = val001
    assemble(db_session, ev)
    minutes = {c: qs.question_set(db_session, p.id).estimated_minutes for c, p in parts.items()}
    assert minutes == {"P001": 32, "P002": 49, "P003": 35, "P004": 54, "P005": 46, "P006": 46, "P007": 26}


def test_approve_is_blocked_by_coverage_gaps_unless_overridden(db_session, val001, monkeypatch) -> None:
    ev, parts, _ = val001
    monkeypatch.setenv("ASSEMBLY_COVERAGE_FLOOR", "30")
    assemble(db_session, ev)
    pset = qs.question_set(db_session, parts["P003"].id)
    gaps = pset.summary["coverage_gaps"]
    assert gaps and all(g["questions"] < 30 for g in gaps)
    with pytest.raises(qa.SetConflict):
        qs.approve_set(db_session, pset, "tester")
    qs.approve_set(db_session, pset, "tester", override_reason="Agreed with the client")
    assert pset.status == "approved" and pset.override_reason == "Agreed with the client"
    assert {q.status for q in _qs(db_session, parts["P003"])} == {"approved"}
    with pytest.raises(qa.SetConflict):
        qs.choose_wording(db_session, _qs(db_session, parts["P003"])[0], "edited", "tester", "Late edit")
    qs.lock_set(db_session, pset)
    assert pset.status == "locked" and {q.status for q in _qs(db_session, parts["P003"])} == {"locked"}


def test_decisions_are_recorded_and_promote_creates_a_draft_bank_version(db_session, val001) -> None:
    ev, parts, _ = val001
    assemble(db_session, ev)
    q = next(q for q in _qs(db_session, parts["P004"]) if _code(db_session, q) == "BOARD-RISK-02")
    q.ai_text, q.ai_reason = "The board reviews risk openly and looks for lessons rather than blame", "Shorter"
    qs.choose_wording(db_session, q, "ai", "Consultant A")
    qs.choose_wording(db_session, q, "bank", "Consultant A")
    qs.choose_wording(db_session, q, "ai", "Consultant B")
    decisions = db_session.execute(select(QuestionSuggestionDecision).where(
        QuestionSuggestionDecision.question_id == q.id).order_by(QuestionSuggestionDecision.decided_at)).scalars().all()
    assert [(d.decision, d.decided_by) for d in decisions] == [
        ("use_ai", "Consultant A"), ("use_bank", "Consultant A"), ("use_ai", "Consultant B")]
    assert all(d.bank_item_code == "BOARD-RISK-02" and d.decided_at for d in decisions)

    report = {r["code"]: r for r in qs.suggestions_report(db_session)}
    assert report["BOARD-RISK-02"]["accepted"] == 2 and report["BOARD-RISK-02"]["offered"] == 1

    item = db_session.get(QuestionBankItem, q.bank_item_id)
    original_text = item.text
    new = qs.promote_to_bank(db_session, item, q, "Consultant B")
    assert new.version == item.version + 1 and new.status == "draft" and new.text == q.text
    assert item.status == "approved" and item.text == original_text
    with pytest.raises(qa.SetConflict):  # an older version can't be promoted again
        qs.promote_to_bank(db_session, item, q, "Consultant B")


def test_api_flow(api_client, db_session, val001, monkeypatch) -> None:
    ev, parts, _ = val001

    class Shared:
        """The test transaction, for the background job (it mustn't close it)."""
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self):
            pass

    monkeypatch.setattr(qa, "session_factory", lambda: Shared())
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/assembly", json={}, headers={"X-Consultant-Name": "Tester"})
    assert r.status_code == 202
    run_id = r.json()["id"]
    run = api_client.get(f"/api/v1/evaluations/{ev.id}/assembly-runs/{run_id}").json()
    assert run["status"] == "done" and run["requested_by"] == "Tester" and run["snapshot_id"]
    assert len(api_client.get(f"/api/v1/evaluations/{ev.id}/assembly-runs").json()["items"]) == 1

    p4 = str(parts["P004"].id)
    body = api_client.get(f"/api/v1/evaluations/{ev.id}/participants/{p4}/question-set").json()
    assert body["set"]["status"] == "draft" and body["set"]["estimated_minutes"] == 54
    assert [s["key"] for s in body["sections"]] == ["board", "committees", "colleagues", "yourself", "confirm"]
    assert body["rater_warnings"][0]["set"] == "ED deep set"
    q = body["sections"][0]["questions"][0]
    r = api_client.patch(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}",
                         json={"use": "edited", "text": "Edited by the consultant"}, headers={"X-Consultant-Name": "Tester"})
    assert r.status_code == 200 and r.json()["text_source"] == "consultant_edited"
    assert r.json()["theme_code"] == q["theme_code"] and r.json()["subject_types"] == q["subject_types"]
    assert api_client.patch(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}",
                            json={"use": "ai"}).status_code == 400  # no AI suggestion
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}/regenerate", json={})
    assert r.status_code == 409  # AI tailoring is off

    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/{p4}/question-set/lock")
    assert r.status_code == 409  # not approved yet
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/{p4}/question-set/approve", json={},
                        headers={"X-Consultant-Name": "Tester"})
    assert r.status_code == 200 and r.json()["set"]["status"] == "approved" and r.json()["set"]["approved_by"] == "Tester"
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/participants/{p4}/question-set/lock")
    assert r.json()["set"]["status"] == "locked"
    assert api_client.patch(f"/api/v1/evaluations/{ev.id}/assembled-questions/{q['id']}",
                            json={"use": "bank"}).status_code == 409

    report = api_client.get("/api/v1/question-bank/suggestions-report").json()["items"]
    assert [(r["code"], r["accepted"], r["edited"], r["offered"]) for r in report] == [(q["bank_item_code"], 0, 1, 0)]
    opts = api_client.put(f"/api/v1/evaluations/{ev.id}/options", json={"options": {"peer_mode": "full"}}).json()
    assert opts["options"]["peer_mode"] == "full"
    assert api_client.put(f"/api/v1/evaluations/{ev.id}/options", json={"options": {"peer_mode": "x"}}).status_code == 400
    assert db_session.scalar(select(func.count()).select_from(AssemblyRun)) == 1
    assert db_session.scalar(select(func.count()).select_from(ParticipantQuestionSet)) == 7

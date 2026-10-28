"""
Analysis of an assembled evaluation on the VAL-001-style fixture with planted
answers (tests/analysis_seed.py): the evidence register, results, suppression,
facts and compliance, computed findings, AI drafts (mocked) and their checks,
runs and comparisons, completion, and legacy evaluations. Placeholder names only.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from app.db.models import (
    AnalysisEvidence,
    BoardMemberFact,
    Evaluation,
    Finding,
    FindingClause,
    FindingEvidence,
    QuestionBankItem,
    Response,
)
from app.domain.board_member_profile import GENERATION_ONLY_KEYS
from app.services import analysis as an
from app.services import analysis_ai as aai
from app.services import question_assembly as qa
from app.services import question_sets as qs
from app.services import tracking
from app.services.governance import fixture_paths, load_clause_fixtures, read_fixture
from app.services.question_bank import load_fixture
from tests.analysis_seed import P002_COMMENTS, seed_planted
from tests.val001 import build_val001

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"
BY = "Consultant A"


def _build(db, monkeypatch, **seed):
    monkeypatch.delenv("AI_TAILORING_ENABLED", raising=False)
    monkeypatch.delenv("AI_ANALYSIS_ENABLED", raising=False)
    monkeypatch.delenv("ASSEMBLY_COVERAGE_FLOOR", raising=False)
    load_clause_fixtures(db, [read_fixture(p) for p in fixture_paths()])
    assert not load_fixture(db, json.loads(FIXTURE.read_text(encoding="utf-8")))["errors"]
    db.execute(update(QuestionBankItem).values(status="approved"))
    db.flush()
    ev, parts, committees = build_val001(db)
    qa.run_assembly(db, qa.create_run(db, ev))
    for p in parts.values():
        qs.approve_set(db, qs.question_set(db, p.id), BY, override_reason="Scope agreed with the client")
    tokens = seed_planted(db, ev, parts, **seed)
    return ev, parts, tokens


@pytest.fixture
def planted(db_session, reference_seeded, monkeypatch):
    return _build(db_session, monkeypatch)


def _run(db, ev, **kw):
    run = an.start_run(db, ev, BY, **kw)
    return an.execute(db, run)


def _subject(run, name):
    return next(s for s in run.results["subjects"].values() if s["name"] == name)


def _findings(db, run, subject=None, rule=None):
    fs = an.findings(db, run)
    if subject is not None:
        fs = [f for f in fs if str(f.evaluation_subject_id) == subject["subject_id"]]
    return [f for f in fs if rule is None or f.rule == rule]


# ----------------------------
# The evidence register
# ----------------------------

def test_one_evidence_row_per_answer_and_in_progress_only_when_asked(db_session, reference_seeded, monkeypatch) -> None:
    ev, parts, _ = _build(db_session, monkeypatch, unsubmitted=("P006",))
    run = _run(db_session, ev)
    submitted_answers = db_session.execute(select(func.count(Response.id)).where(
        Response.evaluation_id == ev.id, Response.participant_id != parts["P006"].id)).scalar()
    rows = db_session.execute(select(AnalysisEvidence).where(AnalysisEvidence.run_id == run.id)).scalars().all()
    assert len(rows) == submitted_answers == run.inputs["evidence_rows"]
    assert len({r.response_id for r in rows}) == len(rows) and not any(r.in_progress for r in rows)
    assert run.results["respondents"] == {"included": 6, "in_progress": 0, "not_included": 1}
    assert {p["category"] for p in run.inputs["participants"]} <= {"chair", "executive", "non_executive",
                                                                     "company_secretary", "independent"}

    run2 = _run(db_session, ev, include_unsubmitted=True)
    rows2 = db_session.execute(select(AnalysisEvidence).where(AnalysisEvidence.run_id == run2.id)).scalars().all()
    assert len(rows2) > len(rows) and any(r.in_progress for r in rows2)
    assert run2.results["respondents"]["in_progress"] == 1 and run2.results["include_unsubmitted"] is True
    assert any(s["in_progress_included"] for s in run2.results["subjects"].values())


# ----------------------------
# Results for the planted data
# ----------------------------

def test_the_planted_numbers(db_session, planted) -> None:
    ev, parts, _ = planted
    run = _run(db_session, ev)
    p5 = _subject(run, "Board Member 005")
    [gap5] = [x for x in p5["self_peer"] if x["code"] == "CORE-05"]
    assert (gap5["self"], gap5["peer_mean"], gap5["peer_raters"], gap5["gap"], gap5["flagged"]) == (3, 4.6, 5, -1.6, True)
    p2 = _subject(run, "Board Member 002")
    [gap2] = [x for x in p2["self_peer"] if x["code"] == "CORE-06"]
    assert (gap2["self"], gap2["peer_mean"], gap2["gap"], gap2["flagged"]) == (5, 2.8, 2.2, True)
    assert sum(not x["flagged"] for x in p2["self_peer"]) == 4  # the other core statements line up

    board = _subject(run, "The board")
    dyn = board["themes"]["BOARD_DYNAMICS"]
    assert dyn["consensus"] == "divided" and dyn["raters"] == 6
    assert dyn["distribution"]["2"] > 0 and dyn["distribution"]["5"] > 0 and dyn["distribution"]["3"] == 0
    eff = board["themes"]["BOARD_EFFECTIVENESS"]
    assert (eff["mean"], eff["consensus"], eff["spread"]) == (5.0, "strong agreement", 0.0)
    ermg = _subject(run, "Enterprise Risk Management and Governance Committee")
    rem = ermg["themes"]["REMUNERATION_NOMINATION"]
    assert rem["mean"] == 2.0 and {it["code"] for it in rem["items"]} >= {"COM-ERMG-02", "COM-ERMG-03"}
    assert any(c["label"] == "NCCG 2018 11.2.5.7" for it in rem["items"] for c in it["clauses"])
    assert p2["comments"] and sorted(c["text"] for cs in p2["comments"].values() for c in cs) == sorted(P002_COMMENTS.values())
    assert all(c["category"] != "Board Member 004" for cs in p2["comments"].values() for c in cs)
    assert board["completion"] == {"eligible": 6, "answered": 6}


def test_small_groups_are_suppressed_and_small_boards_flagged(db_session, planted) -> None:
    ev, _, _ = planted
    run = _run(db_session, ev)
    p3 = _subject(run, "Board Member 003")
    hidden = {k: t for k, t in p3["themes"].items() if t["suppressed"]}
    assert set(hidden) == {"COMPLIANCE_ETHICS", "MANAGEMENT_OVERSIGHT", "RISK_MONITORING"}  # the ED deep set: 2 raters
    for t in hidden.values():
        assert t["raters"] == 2 and t["mean"] is None and t["distribution"] is None and "Only 2 people" in t["suppressed"]
    assert {x["what"] for x in p3["suppressed"]} == {t["label"] for t in hidden.values()}
    split = _subject(run, "The board")["themes"]["BOARD_DYNAMICS"]["split"]
    assert split == {"suppressed": "Not shown: Executives: 2 people (each group needs at least 3)."}
    assert not _findings(db_session, run, p3, "theme_concern") and not _findings(db_session, run, p3, "theme_strength")

    strict = _run(db_session, ev, min_raters=7)
    board = _subject(strict, "The board")
    assert board["small_sample"] is True and board["themes"]["BOARD_EFFECTIVENESS"]["mean"] == 5.0  # flagged, not hidden
    assert "Small sample" in board["notice"]
    p5 = _subject(strict, "Board Member 005")
    assert all(t["suppressed"] for t in p5["themes"].values())
    assert all(sp["peer_mean"] is None and not sp["flagged"] for sp in p5["self_peer"])


def test_facts_never_reach_averages(db_session, planted) -> None:
    ev, _, _ = planted
    run = _run(db_session, ev)
    rows = db_session.execute(select(AnalysisEvidence).where(AnalysisEvidence.run_id == run.id)).scalars().all()
    for sid, res in run.results["subjects"].items():
        for code, t in res["themes"].items():
            counted = [e for e in rows if str(e.evaluation_subject_id) == sid and (e.theme_code or "GENERAL") == code
                       and e.answer_type == "rating" and e.evidence_source_code == "PERCEPTION" and not e.is_self]
            assert t["ratings"] == len(counted), (res["name"], code)
    sec = _subject(run, "The company secretariat")
    assert sec["themes"] == {} and len(sec["facts"]) > 20  # all ORG_FACT: listed, never scored


def test_compliance_gaps_only_from_facts_with_an_expected_answer(db_session, planted) -> None:
    ev, _, _ = planted
    run = _run(db_session, ev)
    sec = _subject(run, "The company secretariat")
    induction = next(f for f in sec["facts"] if f["code"] == "SEC-56")
    assert induction["check"] == {"expected": "Yes", "met": False, "agree": True}
    assert {c["label"] for c in induction["clauses"]} == {"NCCG 2018 13", "NAICOM 2021 3.0"}
    unchecked = next(f for f in sec["facts"] if f["code"] == "SEC-11")  # no expected answer
    assert unchecked["check"] is None
    gaps = [f for f in an.findings(db_session, run) if f.kind == "compliance_gap"]
    [gap] = gaps
    assert gap.bank_item_code == "SEC-56" and "induction programme" in gap.statement
    clauses = db_session.execute(select(FindingClause).where(FindingClause.finding_id == gap.id)).scalars().all()
    assert len(clauses) == 2
    ev_rows = db_session.execute(select(AnalysisEvidence).join(FindingEvidence, FindingEvidence.evidence_id == AnalysisEvidence.id)
                                 .where(FindingEvidence.finding_id == gap.id)).scalars().all()
    assert ev_rows and all(e.evidence_source_code == "ORG_FACT" for e in ev_rows)


def test_an_opinion_answer_never_becomes_a_compliance_gap(db_session, reference_seeded, monkeypatch) -> None:
    # Give an opinion (PERCEPTION) yes/no item an expected answer; answers against it still produce no gap
    load_clause_fixtures(db_session, [read_fixture(p) for p in fixture_paths()])
    load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    db_session.execute(update(QuestionBankItem).where(QuestionBankItem.code == "BOARD-RISK-05").values(expected_answer="no"))
    db_session.flush()
    ev, _, _ = _build(db_session, monkeypatch)
    run = _run(db_session, ev)
    assert all(f.bank_item_code != "BOARD-RISK-05" for f in an.findings(db_session, run) if f.kind == "compliance_gap")
    board = _subject(run, "The board")
    assert all(c["code"] != "BOARD-RISK-05" or c["counts"] for c in board["choices"])


def test_each_planted_pattern_gives_the_expected_finding(db_session, planted) -> None:
    ev, _, _ = planted
    run = _run(db_session, ev)
    kinds = lambda name: {(f.kind, f.rule) for f in _findings(db_session, run, _subject(run, name))}  # noqa: E731
    assert ("self_perception_gap", "self_peer_gap") in kinds("Board Member 005")
    assert ("self_perception_gap", "self_peer_gap") in kinds("Board Member 002")
    assert ("strength", "theme_strength") in kinds("The board")  # meeting management (board effectiveness)
    assert ("observation", "theme_divided") in kinds("The board")  # executives versus everyone else
    assert ("concern", "theme_concern") in kinds("Enterprise Risk Management and Governance Committee")  # succession
    assert ("compliance_gap", "compliance_shortfall") in kinds("The company secretariat")
    divided = _findings(db_session, run, _subject(run, "The board"), "theme_divided")[0]
    assert divided.support == "conflicting"
    gap2 = _findings(db_session, run, _subject(run, "Board Member 002"), "self_peer_gap")[0]
    assert "higher" in gap2.statement and gap2.support == "strong" and gap2.status == "draft" and gap2.origin == "computed"
    concern = _findings(db_session, run, _subject(run, "Enterprise Risk Management and Governance Committee"), "theme_concern")[0]
    assert "11.2.5.7" in concern.statement
    assert db_session.execute(select(FindingClause).where(FindingClause.finding_id == concern.id)).first()
    for f in an.findings(db_session, run):  # every computed finding traces back to answers
        assert db_session.execute(select(FindingEvidence).where(FindingEvidence.finding_id == f.id)).first(), f.statement


# ----------------------------
# AI drafts (mocked)
# ----------------------------

def test_ai_is_off_by_default_and_never_called(db_session, planted) -> None:
    ev, _, _ = planted
    calls = []
    run = an.start_run(db_session, ev, BY, ai=True)
    an.execute(db_session, run, llm_call=lambda s, u: calls.append(1) or "{}")
    assert calls == [] and run.settings["ai_used"] is False and "ai" not in run.results


def test_ai_drafts_are_checked_and_prompts_carry_no_names_or_personality_notes(db_session, planted, monkeypatch) -> None:
    ev, parts, _ = planted
    monkeypatch.setenv("AI_ANALYSIS_ENABLED", "true")
    secret = "PERSONALITY-NOTE-DO-NOT-USE"
    [key] = list(GENERATION_ONLY_KEYS)
    db_session.add(BoardMemberFact(board_member_id=parts["P002"].board_member_id, key=key, value=secret,
                                   source="client", status="confirmed", origin="manual"))
    db_session.flush()
    prompts = []
    p2_name = "Board Member 002"

    def fake(system, user):
        prompts.append(system + user)
        ctx = json.loads(user)
        if "SUBJECTS" in ctx:
            return json.dumps({"conclusion": "The board works well together on meetings; succession needs attention."})
        evidence = ctx["EVIDENCE"]
        if not evidence:
            return json.dumps({"findings": []})
        first = evidence[0]
        comment = next((e for e in evidence if e["answer"] and len(e["answer"].split()) > 4 and not e["fact"]), None)
        drafts = [
            {"kind": "observation", "statement": "Directors broadly agree here.", "support": "limited",
             "evidence_ids": [first["id"]]},
            {"kind": "concern", "statement": "No evidence at all.", "support": "limited", "evidence_ids": []},
            {"kind": "concern", "statement": "Foreign evidence.", "support": "limited",
             "evidence_ids": ["00000000-0000-0000-0000-000000000000"]},
            {"kind": "concern", "statement": "One director said \"this was never said by anyone\".", "support": "limited",
             "evidence_ids": [first["id"]]},
            {"kind": "concern", "statement": "Board Member 004 disagrees strongly.", "support": "limited",
             "evidence_ids": [first["id"]]},
            {"kind": "strength", "statement": "Overstated.", "support": "strong", "evidence_ids": [first["id"]]},
        ]
        if comment:
            drafts.append({"kind": "concern", "statement": f"One colleague wrote \"{comment['answer']}\"",
                           "support": "limited", "evidence_ids": [comment["id"]]})
        return json.dumps({"findings": drafts, "conclusion": "A short draft conclusion."})

    run = an.start_run(db_session, ev, BY, ai=True)
    an.execute(db_session, run, llm_call=fake)
    assert run.settings["ai_used"] is True
    blob = "\n".join(prompts)
    assert secret not in blob
    for p in parts.values():
        assert p.full_name not in blob, p.full_name
    ai = run.results["ai"]
    reasons = {d["reason"].split(":")[0].split(" from ")[0] for d in ai["dropped"]}
    assert {"Cites no evidence.", "Cites evidence that isn't this subject's.", "Quotes text that isn't in the evidence",
            "Names a person other than the subject.", "Claims strong support"} <= reasons
    kept = [f for f in an.findings(db_session, run) if f.origin == "ai"]
    names = {sid: s["name"] for sid, s in run.results["subjects"].items()}
    for f in kept:
        assert f.statement != "Overstated." and "never said" not in f.statement and f.statement != "No evidence at all."
        if "Board Member" in f.statement:  # only ever the subject's own name
            assert f"Board Member 00" in names[str(f.evaluation_subject_id)] and names[str(f.evaluation_subject_id)] in f.statement
    assert any(f.statement == "Directors broadly agree here." for f in kept)
    quoted = [f for f in kept if f.statement.startswith("One colleague wrote")]
    assert any(t in f.statement for f in quoted for t in P002_COMMENTS.values())  # a verbatim quote passes
    assert all(f.status == "draft" for f in kept)
    overall = [c for c in an.conclusions(db_session, run) if c.evaluation_subject_id is None]
    assert overall and overall[0].origin == "ai" and overall[0].status == "draft"
    # The built context itself
    sid = _subject(run, p2_name)["subject_id"]
    context, _ = aai.build_context(db_session, run, sid)
    text = json.dumps(context)
    assert secret not in text and p2_name not in text and context["SUBJECT"]["description"].startswith("the managing")


def test_ai_never_sees_suppressed_results(db_session, planted, monkeypatch) -> None:
    ev, _, _ = planted
    run = _run(db_session, ev)
    p3 = _subject(run, "Board Member 003")
    context, check = aai.build_context(db_session, run, p3["subject_id"])
    hidden = {"COMPLIANCE_ETHICS", "MANAGEMENT_OVERSIGHT", "RISK_MONITORING"}
    assert not [e for e in context["EVIDENCE"] if e["theme_code"] in hidden and not e["fact"]
                and e["category"] != "Self-assessment"]
    assert all(t.get("suppressed") for t in context["RESULTS"]["themes"] if t.get("theme_code") in hidden or "suppressed" in t)


# ----------------------------
# Runs, comparison and completion
# ----------------------------

def test_runs_are_immutable_reruns_are_new_and_comparison_shows_changes(api_client, db_session, planted) -> None:
    ev, parts, tokens = planted
    first = _run(db_session, ev)
    with pytest.raises(an.AnalysisError):
        an.execute(db_session, first)
    # P004 reopens and changes one board effectiveness rating; a new run reflects it
    tracking.reopen_form(db_session, ev, parts["P004"].id, "Late correction", BY)
    data = api_client.get(f"/api/v1/portal/a/{tokens['P004']}").json()
    board_q = next(b for s in data["sections"] if s["key"] == "board" for b in s["blocks"]
                   if b["kind"] == "question" and b["answer_type"] == "rating")
    assert api_client.put(f"/api/v1/portal/a/{tokens['P004']}/answers",
                          json={"answers": [{"question_id": board_q["id"], "value": 1}]}).status_code == 200
    assert api_client.post(f"/api/v1/portal/a/{tokens['P004']}/submit").status_code == 200
    second = _run(db_session, ev)
    assert second.id != first.id and first.status == second.status == "done"
    diff = an.compare(db_session, first, second)
    assert diff["respondents"] == {"before": 7, "after": 7, "added": 0, "removed": 0}
    changed = [c for c in diff["changes"] if c["subject"] == "The board"]
    assert changed and changed[0]["before"]["mean"] != changed[0]["after"]["mean"]
    assert _subject(first, "The board")["themes"] != _subject(second, "The board")["themes"]  # first run unchanged
    r = api_client.get(f"/api/v1/evaluations/{ev.id}/analysis/compare", params={"old": str(first.id), "new": str(second.id)})
    assert r.status_code == 200 and r.json()["changes"]


def test_mark_complete_needs_every_subject_and_the_overall_conclusion(api_client, db_session, planted) -> None:
    ev, _, _ = planted
    run = _run(db_session, ev)
    base = f"/api/v1/evaluations/{ev.id}/analysis/runs/{run.id}"
    blockers = api_client.get(f"{base}/completion").json()["blockers"]
    assert len(blockers) == len(run.results["order"]) + 1
    assert api_client.post(f"{base}/complete").status_code == 409
    for sid in run.results["order"]:
        fs = [f for f in an.findings(db_session, run) if str(f.evaluation_subject_id) == sid]
        if fs:
            r = api_client.patch(f"{base}/findings/{fs[0].id}", json={"status": "accepted"}, headers={"X-Consultant-Name": BY})
            assert r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["edited_by"] == BY
        else:
            r = api_client.put(f"{base}/conclusions", json={"subject_id": sid, "no_findings": True,
                                                             "text": "Nothing to report.", "status": "accepted"})
            assert r.status_code == 200 and r.json()["no_findings"] is True
    assert api_client.get(f"{base}/completion").json()["blockers"] == ["Write and accept the overall conclusion."]
    assert api_client.put(f"{base}/conclusions", json={"status": "accepted"}).status_code == 422  # nothing written
    api_client.put(f"{base}/conclusions", json={"text": "The board works well; succession needs attention.", "status": "accepted"})
    r = api_client.post(f"{base}/complete", headers={"X-Consultant-Name": BY})
    assert r.status_code == 200 and r.json()["completed_by"] == BY
    f = an.findings(db_session, run)[0]
    assert api_client.patch(f"{base}/findings/{f.id}", json={"status": "rejected"}).status_code == 409  # complete: frozen


def test_findings_api_edit_keeps_the_original_add_and_evidence(api_client, db_session, planted) -> None:
    ev, _, _ = planted
    run = _run(db_session, ev)
    base = f"/api/v1/evaluations/{ev.id}/analysis/runs/{run.id}"
    p2 = _subject(run, "Board Member 002")
    fs = api_client.get(f"{base}/findings", params={"subject_id": p2["subject_id"]}).json()["findings"]
    gap = next(f for f in fs if f["kind"] == "self_perception_gap")
    r = api_client.patch(f"{base}/findings/{gap['finding_id']}", json={"statement": "Rates their openness to challenge far above colleagues."})
    assert r.json()["status"] == "edited" and r.json()["original_text"] == gap["statement"]
    ev_list = api_client.get(f"{base}/subjects/{p2['subject_id']}/evidence").json()
    assert ev_list["evidence"] and all(set(e) >= {"question", "category", "value"} for e in ev_list["evidence"])
    # One chair, two executives, two NEDs: with a minimum of 3, no opinion carries a category that points at someone
    opinions = {e["category"] for e in ev_list["evidence"] if not e["fact"]}
    assert opinions <= {"Director", "Self-assessment"}
    assert all(c["category"] in ("Director", "Self-assessment") for cs in p2["comments"].values() for c in cs)
    blob = json.dumps(ev_list)
    assert "Board Member 00" not in blob.replace("Board Member 002", "")  # only the subject's own name, in the header
    added = api_client.post(f"{base}/findings", json={"subject_id": p2["subject_id"], "kind": "observation",
                                                      "statement": "Discussed with the chair.", "support": "limited",
                                                      "evidence_ids": [ev_list["evidence"][0]["evidence_id"]]})
    assert added.status_code == 201 and added.json()["origin"] == "consultant" and added.json()["evidence_count"] == 1
    other = _subject(run, "Board Member 005")
    foreign = api_client.get(f"{base}/subjects/{other['subject_id']}/evidence").json()["evidence"][0]["evidence_id"]
    bad = api_client.post(f"{base}/findings", json={"subject_id": p2["subject_id"], "kind": "observation", "statement": "x",
                                                    "support": "limited", "evidence_ids": [foreign, "nope"]})
    assert bad.status_code == 422


def test_api_runs_in_the_background(api_client, db_session, planted, monkeypatch) -> None:
    ev, _, _ = planted

    class Shared:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self):
            pass

    monkeypatch.setattr(an, "session_factory", lambda: Shared())
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/analysis/runs", json={"min_raters": 3})
    assert r.status_code == 202
    run = api_client.get(f"/api/v1/evaluations/{ev.id}/analysis/runs/{r.json()['run_id']}").json()
    assert run["status"] == "done" and run["results"]["subjects"] and run["blockers"]
    assert api_client.post(f"/api/v1/evaluations/{ev.id}/analysis/runs", json={"min_raters": 1}).status_code == 409


def test_legacy_evaluations_keep_analytics_and_assembled_ones_are_pointed_on(api_client, db_session, planted) -> None:
    ev, _, _ = planted
    r = api_client.get(f"/api/v1/evaluations/{ev.id}/analytics")
    assert r.status_code == 409 and "/analysis/runs" in r.json()["detail"]
    legacy = Evaluation(id="LEGACY-A", tenant_name="Legacy Co", sector="insurance", year=2025, regulators={"items": []})
    db_session.add(legacy)
    db_session.flush()
    assert api_client.get(f"/api/v1/evaluations/{legacy.id}/analytics").status_code == 200
    assert api_client.get(f"/api/v1/evaluations/{legacy.id}/analysis/runs").status_code == 409

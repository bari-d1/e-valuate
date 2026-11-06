"""
The evaluation report (app.services.reporting, app.api.reports): built only from
the latest completed analysis run's approved findings and conclusions, every
finding traceable to evidence in that run, no respondent named in the JSON or
the Word file, and no report without a completed analysis. Reports saved in the
earlier layout still export. Placeholder names only.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import io
import json

import pytest
from docx import Document
from sqlalchemy import select

from app.db.models import AnalysisEvidence, Evaluation, Report
from app.services import analysis as an
from app.services import reporting
from tests.test_analysis import BY, _build, _run

pytestmark = pytest.mark.integration


@pytest.fixture
def planted(db_session, reference_seeded, monkeypatch):
    return _build(db_session, monkeypatch)


def _decide_and_complete(db, run, before_complete=None):
    """Per subject: accept one finding, reject one, leave the rest as drafts; then complete the run."""
    decided = {"accepted": [], "rejected": [], "draft": []}
    for sid in run.results["order"]:
        fs = [f for f in an.findings(db, run) if str(f.evaluation_subject_id) == sid]
        if not fs:
            an.set_conclusion(db, run, BY, subject_id=sid, no_findings=True, text="Nothing to report.", status="accepted")
            continue
        an.update_finding(db, run, fs[0], BY, status="accepted")
        decided["accepted"].append(fs[0])
        if len(fs) > 1:
            an.update_finding(db, run, fs[1], BY, status="rejected")
            decided["rejected"].append(fs[1])
        decided["draft"] += fs[2:]
    board = next(sid for sid in run.results["order"] if run.results["subjects"][sid]["kind"] == "board")
    an.set_conclusion(db, run, BY, subject_id=board, text="The board works well in meetings.", status="accepted")
    unbacked = an.add_finding(db, run, BY, subject_id=board, kind="observation", statement="Not yet evidenced.",
                              support="limited")
    decided["draft"].append(unbacked)
    an.set_conclusion(db, run, BY, subject_id=None, text="Meetings work well; succession needs attention.",
                      status="accepted")
    if before_complete:
        before_complete(decided)
    an.mark_complete(db, run, BY)
    return decided


def _generate(api_client, ev):
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/report/generate", json={"include_trends": True})
    assert r.status_code == 201, r.text
    rid = r.json()["report_id"]
    return rid, api_client.get(f"/api/v1/reports/{rid}").json()["summary_json"]


def _docx_text(api_client, rid) -> str:
    r = api_client.get(f"/api/v1/reports/{rid}/docx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    doc = Document(io.BytesIO(r.content))
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    return "\n".join([p.text for p in doc.paragraphs] + cells)


def test_no_report_without_a_completed_analysis(api_client, db_session, planted) -> None:
    ev, _, _ = planted
    url = f"/api/v1/evaluations/{ev.id}/report/generate"
    r = api_client.post(url, json={})
    assert r.status_code == 409 and "no completed analysis" in r.json()["detail"]
    _run(db_session, ev)  # finished, but not marked complete
    assert api_client.post(url).status_code == 409
    legacy = Evaluation(id="LEGACY-R", tenant_name="Legacy Co", sector="insurance", year=2025, regulators={"items": []})
    db_session.add(legacy)
    db_session.flush()
    assert api_client.post("/api/v1/evaluations/LEGACY-R/report/generate", json={}).status_code == 409
    assert api_client.post("/api/v1/evaluations/NO-SUCH-EVAL/report/generate", json={}).status_code == 404
    assert db_session.get(Evaluation, "NO-SUCH-EVAL") is None  # no demo evaluation is created any more
    assert not hasattr(reporting, "_demo_analytics") and not hasattr(reporting, "_mvp_context")


def test_the_report_holds_only_approved_findings_each_traced_to_the_run(api_client, db_session, planted) -> None:
    ev, _, _ = planted
    older = _run(db_session, ev)
    _decide_and_complete(db_session, older)
    run = _run(db_session, ev)
    edit = lambda d: an.update_finding(db_session, run, d["accepted"][0], BY,  # noqa: E731
                                       statement=d["accepted"][0].statement + " Noted by the consultant.")
    decided = _decide_and_complete(db_session, run, before_complete=edit)
    edited = decided["accepted"][0]
    assert edited.status in an.ACCEPTED

    rid, report = _generate(api_client, ev)
    trace = report["traceability"]
    assert report["schema_version"] == 2 and report["grouped_by"] == "subject"
    assert trace["run_id"] == str(run.id) and trace["report_id"] == rid  # the latest completed run
    assert trace["analysis_settings"]["thresholds"] == run.settings["thresholds"]
    assert trace["analysis_settings"]["thresholds_status"] == "unapproved"
    assert trace["generated_at"] and trace["run_completed_by"] == BY

    findings = [f for s in report["subjects"] for f in s["findings"]] + report["overall"]["findings"]
    assert {f["finding_id"] for f in findings} == {str(f.id) for f in decided["accepted"]} == set(trace["finding_ids"])
    blob = json.dumps(report)
    for f in decided["rejected"] + decided["draft"]:
        assert str(f.id) not in blob, f.statement
    assert next(f for f in findings if f["finding_id"] == str(edited.id))["statement"].endswith("Noted by the consultant.")

    evidence = {str(e.id): e for e in db_session.execute(select(AnalysisEvidence)).scalars()}
    for f in findings:
        assert f["evidence"], f["statement"]
        assert {"kind", "statement", "support", "clauses", "theme_code"} <= set(f)
        for e in f["evidence"]:
            assert str(evidence[e["evidence_id"]].run_id) == trace["run_id"]
            assert set(e) == {"evidence_id", "question", "respondent_category", "respondent", "theme_code"}
            assert e["respondent"].startswith("R")

    assert [s["subject_id"] for s in report["subjects"]] == run.results["order"]
    assert report["overall"]["conclusion"]["text"] == "Meetings work well; succession needs attention."
    assert next(s for s in report["subjects"] if s["kind"] == "board")["conclusion"]["text"] == "The board works well in meetings."
    assert all(f["kind"] != "compliance_gap" and "compliance" not in f["kind_label"].lower() for f in findings)


def test_no_respondent_is_named_in_the_report_or_the_word_file(api_client, db_session, planted) -> None:
    ev, parts, _ = planted
    run = _run(db_session, ev)
    _decide_and_complete(db_session, run)
    rid, report = _generate(api_client, ev)
    text = _docx_text(api_client, rid)
    blob = json.dumps(report)
    for p in parts.values():
        for where, content in (("summary_json", blob), ("docx", text)):
            assert p.full_name not in content, (where, p.full_name)
            assert p.email not in content, (where, p.email)
    names = {s["name"] for s in report["subjects"] if s["kind"] == "person"}
    assert "the chair" in names and "the managing director / CEO" in names
    # The Word file carries the structure, the evidence behind each finding and the traceability
    assert "Overall conclusion" in text and "Appendix: traceability" in text and str(run.id) in text
    assert text.count("Evidence (") == len(report["traceability"]["finding_ids"])


def test_subjects_of_the_same_role_get_distinct_labels() -> None:
    results = {"order": ["a", "b", "c", "d"], "subjects": {
        "a": {"kind": "board", "type": "BOARD", "name": "The board"},
        "b": {"kind": "person", "type": "ED", "name": "Person One"},
        "c": {"kind": "person", "type": "ED", "name": "Person Two"},
        "d": {"kind": "person", "type": "CHAIR", "name": "Person Three"}}}
    assert reporting.subject_labels(results) == {"a": "The board", "b": "executive director A",
                                                 "c": "executive director B", "d": "the chair"}
    swap = reporting._Names(["Person One", "Someone Else"], {"Person Two": "executive director B"})
    assert swap("Person Two rates themselves high; Someone Else disagrees.") == \
        "Executive director B rates themselves high; [name] disagrees."


def test_reports_saved_in_the_earlier_layout_still_export(api_client, db_session, planted) -> None:
    ev, _, _ = planted
    old = Report(id="old-layout-report", evaluation_id=ev.id, created_by="someone", status="draft", summary_json={
        "analytics": {"evaluation": {"tenant_name": "Old Co"}, "metrics": {}, "trends": {"available": False}},
        "context": {}, "sections": {"executive_summary": {"overall_message": "Earlier report."},
                                    "recommendations": {"recommendations": []}}})
    db_session.add(old)
    db_session.flush()
    assert "Earlier report." in _docx_text(api_client, old.id)

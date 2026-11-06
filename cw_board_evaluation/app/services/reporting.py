"""
app.services.reporting
----------------------
The evaluation report, built only from the consultant's decisions on the latest
completed analysis run (app.services.analysis), never from raw analytics:
report content comes from approved findings and the evidence they cite, and
every finding stays traceable (methodology spec v1.1).

What goes in (generate_report_for_evaluation):
- the latest run marked complete; none means no report (ReportError);
- the approved overall conclusion;
- one section per subject, in the analysis order (the board, committees,
  individual directors, the secretariat), with its approved conclusion and its
  approved (accepted or edited) findings that cite evidence. Draft and rejected
  findings never appear;
- for each finding: kind, statement, support, theme_code (so a later grouping by
  dimension can be added without changing this shape), linked clauses, and
  evidence references (evidence id, question, respondent category and the run's
  pseudonym; never a name, and not the answer text);
- traceability: run id, the finding and conclusion ids used, the run's settings
  (min_raters, thresholds, thresholds_status...) and when the report was made.

No respondent is named. Individual directors are subjects and respondents at
once, so in the report they appear by role ("the chair", "executive director A"),
and any person's name in a statement, conclusion or question is replaced the same
way (another person's name becomes "[name]").

AI is not used here. Polishing the executive summary with AI is a follow-up: it
needs a check that the polished text adds no finding.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisEvidence,
    AnalysisRun,
    Evaluation,
    Finding,
    FindingClause,
    FindingEvidence,
    GovernanceClause,
)
from app.domain import analysis_rules as R
from app.services import analysis as an

SCHEMA_VERSION = 2
KIND_ORDER = ("practice_gap", "concern", "self_perception_gap", "observation", "strength")
KIND_LABELS = {
    "strength": "Strength", "concern": "Concern", "observation": "Observation",
    "practice_gap": "Practice differs from expectation (unverified)", "self_perception_gap": "Self-perception gap",
}
SUPPORT_LABELS = {"strong": "Strong support", "moderate": "Moderate support", "limited": "Limited support",
                  "conflicting": "Conflicting views"}
DRAFT_SIGNAL_KINDS = ("strength", "concern", "self_perception_gap")
ROLE_LABELS = {"CHAIR": "the chair", "MD_CEO": "the managing director / CEO", "ED": "executive director",
               "NED": "non-executive director", "INED": "independent non-executive director"}


class ReportError(ValueError):
    """The report can't be generated now. The message is safe to show the consultant."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def llm_sanity_check() -> Dict[str, Any]:
    """
    Quick check: can we call the configured LLM successfully?
    Returns minimal data to confirm call works.
    """
    from langchain.chat_models import init_chat_model
    from langchain_core.messages import HumanMessage

    chosen_model = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required for real LLM calls.")

    llm = init_chat_model(
        chosen_model,
        model_provider="openai",
        api_key=api_key,
        temperature=0,
    )
    resp = llm.invoke([HumanMessage(content="Reply with exactly: pong")])
    return {"ping": (getattr(resp, "content", "") or "").strip()}


# ----------------------------
# Choosing the run
# ----------------------------

def latest_completed_run(db: Session, evaluation_id: str) -> Optional[AnalysisRun]:
    return db.execute(select(AnalysisRun).where(AnalysisRun.evaluation_id == evaluation_id,
                                                AnalysisRun.completed_at.is_not(None))
                      .order_by(AnalysisRun.completed_at.desc()).limit(1)).scalars().first()


# ----------------------------
# Names
# ----------------------------

def subject_labels(results: Dict[str, Any]) -> Dict[str, str]:
    """How each subject is named in the report: by role for individual directors, by name otherwise."""
    out: Dict[str, str] = {}
    by_type: Dict[str, List[str]] = {}
    for sid in results["order"]:
        res = results["subjects"][sid]
        if res["kind"] == "person":
            by_type.setdefault(res["type"], []).append(sid)
        else:
            out[sid] = res["name"]
    for code, sids in by_type.items():
        role = ROLE_LABELS.get(code, "director")
        for n, sid in enumerate(sids):
            out[sid] = role if len(sids) == 1 and role.startswith("the ") else f"{role} {chr(ord('A') + n)}"
    return out


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


class _Names:
    """Replaces people's names: a subject's own name by its role label, anyone else's by "[name]"."""

    def __init__(self, names: List[str], own: Dict[str, str]):
        self.own = {k.lower(): v for k, v in own.items()}
        everyone = sorted(set(names) | set(own), key=len, reverse=True)
        self.pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in everyone) + r")\b", re.IGNORECASE) \
            if everyone else None

    def __call__(self, text: Optional[str]) -> Optional[str]:
        if not text or self.pattern is None:
            return text

        def swap(m: "re.Match[str]") -> str:
            label = self.own.get(m.group(0).lower(), "[name]")
            start = m.start() == 0 or text[:m.start()].rstrip().endswith((".", "!", "?", ":"))
            return _cap(label) if start else label

        return self.pattern.sub(swap, text)


# ----------------------------
# Building the report
# ----------------------------

def _clauses(db: Session, finding_ids: List) -> Dict[Any, List[Dict[str, Any]]]:
    out: Dict[Any, List[Dict[str, Any]]] = {}
    if not finding_ids:
        return out
    for link, c in db.execute(select(FindingClause, GovernanceClause)
                              .join(GovernanceClause, GovernanceClause.id == FindingClause.clause_id)
                              .where(FindingClause.finding_id.in_(finding_ids))).all():
        out.setdefault(link.finding_id, []).append(
            {"clause_id": str(c.id), "label": an.clause_label(c), "heading": c.heading})
    return out


def _evidence(db: Session, run: AnalysisRun, finding_ids: List) -> Dict[Any, List[AnalysisEvidence]]:
    """Each finding's cited evidence, from this run only."""
    out: Dict[Any, List[AnalysisEvidence]] = {}
    if not finding_ids:
        return out
    rows = db.execute(select(FindingEvidence.finding_id, AnalysisEvidence)
                      .join(AnalysisEvidence, AnalysisEvidence.id == FindingEvidence.evidence_id)
                      .where(FindingEvidence.finding_id.in_(finding_ids), AnalysisEvidence.run_id == run.id)
                      .order_by(AnalysisEvidence.bank_item_code, AnalysisEvidence.respondent_ref)).all()
    for fid, e in rows:
        out.setdefault(fid, []).append(e)
    return out


def _finding(f: Finding, run: AnalysisRun, evidence: List[AnalysisEvidence], clauses: List[Dict[str, Any]],
             themes: Dict[str, str], names: _Names, unapproved: bool) -> Dict[str, Any]:
    return {
        "finding_id": str(f.id), "kind": f.kind, "kind_label": KIND_LABELS.get(f.kind, f.kind),
        "statement": names(f.statement), "support": f.support, "support_label": SUPPORT_LABELS.get(f.support, f.support),
        "theme_code": f.theme_code, "theme_label": themes.get(f.theme_code) if f.theme_code else None,
        "origin": f.origin, "status": f.status,
        # Drafted from thresholds the client hasn't approved (app.domain.analysis_rules)
        "draft_signal": f.origin == "computed" and f.kind in DRAFT_SIGNAL_KINDS and unapproved,
        "clauses": clauses,
        "evidence": [{"evidence_id": str(e.id), "question": names(e.question_text),
                      "respondent_category": an.category_label(run, e), "respondent": e.respondent_ref,
                      "theme_code": e.theme_code} for e in evidence],
    }


def _conclusion(c, names: _Names) -> Optional[Dict[str, Any]]:
    if c is None or c.status not in an.ACCEPTED:
        return None
    return {"conclusion_id": str(c.id), "text": names(c.text), "no_findings": c.no_findings}


def build_report(db: Session, ev: Evaluation, run: AnalysisRun, *, generated_by: str) -> Dict[str, Any]:
    """The report's summary_json from a completed run's approved findings and conclusions."""
    from app.services.analysis_ai import people_names

    results = run.results
    labels = subject_labels(results)
    own = {results["subjects"][sid]["name"]: labels[sid] for sid in results["order"]
           if results["subjects"][sid]["kind"] == "person"}
    names = _Names(people_names(db, ev), own)
    unapproved = run.settings.get("thresholds_status", R.THRESHOLDS_UNAPPROVED) != "approved"
    themes = {code: t["label"] for res in results["subjects"].values() for code, t in res["themes"].items()}

    approved = [f for f in an.findings(db, run) if f.status in an.ACCEPTED]
    ids = [f.id for f in approved]
    evidence, clauses = _evidence(db, run, ids), _clauses(db, ids)
    used = [f for f in approved if evidence.get(f.id)]  # every finding in the report cites evidence
    order = lambda f: (KIND_ORDER.index(f.kind) if f.kind in KIND_ORDER else 99, f.created_at, str(f.id))  # noqa: E731
    used.sort(key=order)
    as_dict = lambda f: _finding(f, run, evidence[f.id], clauses.get(f.id, []), themes, names, unapproved)  # noqa: E731

    cs = {str(c.evaluation_subject_id) if c.evaluation_subject_id else None: c for c in an.conclusions(db, run)}
    subjects = []
    for sid in results["order"]:
        res = results["subjects"][sid]
        subjects.append({
            "subject_id": sid, "name": labels[sid], "type": res["type"], "kind": res["kind"],
            "conclusion": _conclusion(cs.get(sid), names),
            "findings": [as_dict(f) for f in used if str(f.evaluation_subject_id) == sid],
        })
    overall = _conclusion(cs.get(None), names)
    general = [as_dict(f) for f in used if f.evaluation_subject_id is None]

    return {
        "schema_version": SCHEMA_VERSION,
        "grouped_by": "subject",
        "evaluation": {"id": ev.id, "name": ev.name, "organisation": ev.tenant_name, "year": ev.year},
        "overall": {"conclusion": overall, "findings": general},
        "subjects": subjects,
        "ai_summary": None,
        "traceability": {
            "evaluation_id": ev.id, "run_id": str(run.id),
            "run_completed_at": an._iso(run.completed_at), "run_completed_by": run.completed_by,
            "finding_ids": [str(f.id) for f in used],
            "conclusion_ids": [c["conclusion_id"] for c in [overall, *(s["conclusion"] for s in subjects)] if c],
            "analysis_settings": dict(run.settings),
            "respondents": results.get("respondents"),
            "generated_at": _now().isoformat(), "generated_by": generated_by,
        },
    }


def generate_report_for_evaluation(db: Session, evaluation_id: str, user_id: str) -> Dict[str, Any]:
    """summary_json for a new report; ReportError when there's no completed analysis to build it from."""
    ev = db.get(Evaluation, evaluation_id)
    if ev is None:
        raise LookupError("Evaluation not found.")
    run = latest_completed_run(db, evaluation_id)
    if run is None:
        raise ReportError(
            "There's no completed analysis for this evaluation. The report is built only from approved findings: "
            "run the analysis on the Findings page, decide the findings, and mark the analysis complete first.")
    return build_report(db, ev, run, generated_by=user_id)

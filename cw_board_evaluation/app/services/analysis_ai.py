"""
app.services.analysis_ai
------------------------
AI drafting of findings and conclusions (drafts only; a consultant accepts,
edits or rejects every one). Off unless AI_ANALYSIS_ENABLED is true: response
data is the most sensitive data in the system.

What the model sees, per subject (build_context): that subject's results,
facts and compliance checks, the evidence it may cite (respondent category and
a per-run pseudonym, never names; comments only where the group is big enough;
nothing from suppressed results), the related clause texts, the organisation's
confirmed context, the subject's confirmed profile without generation-only notes,
and the evaluation brief. Names are replaced with "[name]" wherever they appear.

Every draft is checked in code (validate). A finding is dropped when it:
  - cites no evidence, or evidence that isn't this subject's;
  - quotes text (in double quotes) that doesn't appear word for word in the cited
    evidence or its questions;
  - names a person other than the subject;
  - claims more support than its evidence allows: strong needs >= 5 distinct
    respondents, moderate >= 3, conflicting >= 2 (app.domain.analysis_rules);
  - is a compliance_gap that doesn't rest on a factual answer.
Clause ids the subject doesn't relate to are removed. Dropped drafts and the
reason are kept on the run so the consultant can see them.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.prompts.analysis_synthesis import (
    OVERALL_SYSTEM_PROMPT,
    SUBJECT_SYSTEM_PROMPT,
    overall_user_prompt,
    subject_user_prompt,
)
from app.db.models import (
    AnalysisEvidence,
    AnalysisRun,
    BoardMember,
    Conclusion,
    Evaluation,
    Finding,
    FindingClause,
    FindingEvidence,
    OrganisationFact,
    Participant,
)
from app.domain import analysis_rules as R
from app.domain.org_profile import FACTS_BY_KEY
from app.domain.question_rules import format_fact_value
from app.services import analysis as an

LLMCall = Callable[[str, str], str]  # (system, user) -> raw text reply

ROLE_WORDS = {"BOARD": "the board as a whole", "COMMITTEE": "a board committee", "CHAIR": "the chair",
              "MD_CEO": "the managing director / CEO", "ED": "an executive director",
              "NED": "a non-executive director", "INED": "an independent non-executive director",
              "COMPANY_SECRETARY": "the company secretariat"}


def enabled() -> bool:
    return (os.getenv("AI_ANALYSIS_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def default_llm_call(system: str, user: str) -> str:
    from app.services.org_extraction import default_llm_call as call
    return call(system, user)


class DraftFinding(BaseModel):
    kind: Literal["strength", "concern", "observation", "compliance_gap", "self_perception_gap"]
    statement: str = Field(min_length=1, max_length=800)
    support: Literal["strong", "moderate", "limited", "conflicting"]
    evidence_ids: List[str] = Field(default_factory=list)
    clause_ids: List[str] = Field(default_factory=list)
    theme_code: Optional[str] = None


class SubjectDraft(BaseModel):
    findings: List[DraftFinding] = Field(default_factory=list)
    conclusion: Optional[str] = Field(default=None, max_length=2000)


class OverallDraft(BaseModel):
    conclusion: str = Field(min_length=1, max_length=3000)


def _parse(raw: str) -> Any:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s.lower().startswith("json"):
            s = s[4:].strip()
    return json.loads(s)


# ----------------------------
# Names
# ----------------------------

def people_names(db: Session, ev: Evaluation) -> List[str]:
    """Every person's name the evaluation knows: participants and the organisation's board members."""
    names = {p.full_name for p in db.execute(select(Participant).where(Participant.evaluation_id == ev.id)).scalars()
             if p.full_name}
    if ev.organisation_id:
        names |= {m.full_name for m in db.execute(select(BoardMember).where(
            BoardMember.organisation_id == ev.organisation_id)).scalars() if m.full_name}
    return sorted(names, key=len, reverse=True)


def scrub(text: Optional[str], names: List[str]) -> Optional[str]:
    if not text:
        return text
    for n in names:
        text = re.sub(re.escape(n), "[name]", text, flags=re.IGNORECASE)
    return text


def mentions(text: str, names: List[str]) -> List[str]:
    return [n for n in names if re.search(r"\b" + re.escape(n) + r"\b", text, flags=re.IGNORECASE)]


# ----------------------------
# Context
# ----------------------------

def _allowed_evidence(res: Dict[str, Any], rows: List[AnalysisEvidence]) -> List[AnalysisEvidence]:
    """The subject's evidence the model may see: nothing from suppressed results or hidden comments."""
    suppressed_themes = {code for code, t in res["themes"].items() if t["suppressed"]}
    suppressed_items = {it["code"] for t in res["themes"].values() for it in t["items"] if it["suppressed"]}
    suppressed_choices = {c["code"] for c in res["choices"] if c["suppressed"]}
    out = []
    for e in rows:
        key = e.bank_item_code or e.question_text
        if an._is_fact(e):
            out.append(e)
        elif e.answer_type == "comment":
            if res["comments_suppressed"] and not e.is_self:
                continue
            out.append(e)
        elif e.answer_type == "rating":
            if e.is_self:
                out.append(e)  # the subject's own self-rating
            elif (e.theme_code or "GENERAL") not in suppressed_themes and key not in suppressed_items:
                out.append(e)
        elif key not in suppressed_choices:
            out.append(e)
    return out


def _org_context(db: Session, ev: Evaluation) -> Dict[str, Any]:
    facts = {}
    if ev.organisation_id:
        for f in db.execute(select(OrganisationFact).where(OrganisationFact.organisation_id == ev.organisation_id,
                                                           OrganisationFact.status == "confirmed")).scalars():
            facts[FACTS_BY_KEY.get(f.key, {}).get("label", f.key)] = format_fact_value(f.value)
    return {"organisation_facts": facts, "evaluation_brief": ev.brief or "",
            "review_period_end": ev.review_period_end.isoformat() if ev.review_period_end else None}


def build_context(db: Session, run: AnalysisRun, subject_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(the prompt context, what the validator needs). No names, no generation-only notes."""
    ev = db.get(Evaluation, run.evaluation_id)
    res = run.results["subjects"][subject_id]
    names = people_names(db, ev)
    rows = an.subject_evidence(db, run, subject_id)
    allowed = _allowed_evidence(res, rows)
    clauses = {}
    for t in res["themes"].values():
        for it in t["items"]:
            for c in it["clauses"]:
                clauses[c["clause_id"]] = c
    for f in res["facts"]:
        for c in f["clauses"]:
            clauses[c["clause_id"]] = c
    describe = ROLE_WORDS.get(res["type"], "the subject")
    if res["kind"] == "committee":
        describe = f"a board committee: {res['name']}"
    themes = []
    for code, t in res["themes"].items():
        if t["suppressed"]:
            themes.append({"theme": t["label"], "suppressed": t["suppressed"]})
            continue
        themes.append({
            "theme": t["label"], "theme_code": code, "average": t["mean"], "raters": t["raters"],
            "agreement": t["consensus"], "distribution": t["distribution"],
            "groups": (t.get("split") or {}).get("groups"),
            "items": [{"question": scrub(it["question"], names), "average": it["mean"], "raters": it["raters"],
                       "agreement": it["consensus"]} for it in t["items"] if not it["suppressed"]],
        })
    context = {
        "SUBJECT": {"description": describe, "small_sample": res["small_sample"],
                    "raters": res["raters"], "minimum_raters": run.results["min_raters"]},
        "RESULTS": {
            "themes": themes,
            "self_versus_peer": [{"statement": sp["statement"], "self": sp["self"], "peer_average": sp["peer_mean"],
                                  "peer_raters": sp["peer_raters"], "gap": sp["gap"]}
                                 for sp in res["self_peer"] if not sp["suppressed"]],
            "yes_no_and_choices": [{"question": scrub(c["question"], names), "counts": c["counts"]}
                                   for c in res["choices"] if not c["suppressed"]],
        },
        "FACTS": [{"question": scrub(f["question"], names),
                   "answers": [{"category": a["category"], "answer": scrub(a["value"], names)} for a in f["answers"]],
                   "check": f["check"], "clause_ids": [c["clause_id"] for c in f["clauses"]]} for f in res["facts"]],
        "EVIDENCE": [{"id": str(e.id), "question": scrub(e.question_text, names),
                      "category": an.category_label(run, e),
                      "respondent": e.respondent_ref, "answer": scrub(an.value_text(e.value), names),
                      "fact": an._is_fact(e), "theme_code": e.theme_code} for e in allowed],
        "CLAUSES": [{"id": cid, "label": c["label"], "heading": c["heading"], "text": (c["text"] or "")[:1200]}
                    for cid, c in clauses.items()],
        "CONTEXT": {**_org_context(db, ev),
                    "subject_profile": {f["label"]: scrub(f["value"], names) for f in res.get("profile_facts", [])}},
    }
    check = {
        "evidence": {str(e.id): e for e in allowed}, "clause_ids": set(clauses),
        "subject_name": res["name"] if res["kind"] == "person" else None,
        "other_names": [n for n in names if n.lower() != (res["name"] or "").lower()],
    }
    return context, check


# ----------------------------
# Validation
# ----------------------------

QUOTE = re.compile(r"[\"“”]([^\"“”]{3,})[\"“”]")


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def validate(draft: DraftFinding, check: Dict[str, Any]) -> Tuple[Optional[DraftFinding], Optional[str]]:
    """(the draft, cleaned) if it passes, else (None, why it was dropped)."""
    if not draft.evidence_ids:
        return None, "Cites no evidence."
    rows = [check["evidence"].get(i) for i in draft.evidence_ids]
    if any(r is None for r in rows):
        return None, "Cites evidence that isn't this subject's."
    texts = [_norm(an.value_text(r.value)) for r in rows] + [_norm(r.question_text) for r in rows]
    for q in QUOTE.findall(draft.statement):
        if not any(_norm(q) in t for t in texts):
            return None, f"Quotes text that isn't in the evidence: \"{q[:80]}\"."
    named = mentions(draft.statement, check["other_names"])
    if named:
        return None, "Names a person other than the subject."
    people = len({r.respondent_ref for r in rows})
    if not R.support_allowed(draft.support, people):
        return None, f"Claims {draft.support} support from {people} respondent{'' if people == 1 else 's'}."
    if draft.kind == "compliance_gap" and not any(an._is_fact(r) for r in rows):
        return None, "A compliance gap must rest on a factual answer, not opinions."
    draft.clause_ids = [c for c in draft.clause_ids if c in check["clause_ids"]]
    return draft, None


# ----------------------------
# Drafting
# ----------------------------

def draft(db: Session, run: AnalysisRun, llm_call: Optional[LLMCall] = None) -> Dict[str, Any]:
    """Draft findings and a conclusion per subject, then the overall conclusion. Records what was dropped."""
    call = llm_call or default_llm_call
    kept, dropped, calls = 0, [], 0
    for sid in run.results["order"]:
        context, check = build_context(db, run, sid)
        if not context["EVIDENCE"]:
            continue
        calls += 1
        name = run.results["subjects"][sid]["name"]
        try:
            reply = SubjectDraft.model_validate(_parse(call(SUBJECT_SYSTEM_PROMPT, subject_user_prompt(context))))
        except (ValueError, ValidationError) as e:
            dropped.append({"subject": name, "statement": None, "reason": f"The reply couldn't be read: {str(e)[:120]}"})
            continue
        for d in reply.findings:
            ok, why = validate(d, check)
            if ok is None:
                dropped.append({"subject": name, "statement": d.statement, "reason": why})
                continue
            f = Finding(run_id=run.id, evaluation_subject_id=sid, theme_code=ok.theme_code, kind=ok.kind,
                        statement=ok.statement.strip(), support=ok.support, origin="ai", status="draft",
                        original_text=ok.statement.strip(), rule="ai")
            db.add(f)
            db.flush()
            for eid in dict.fromkeys(ok.evidence_ids):
                db.add(FindingEvidence(finding_id=f.id, evidence_id=eid))
            for cid in dict.fromkeys(ok.clause_ids):
                db.add(FindingClause(finding_id=f.id, clause_id=cid))
            kept += 1
        text = (reply.conclusion or "").strip()
        if text and not mentions(text, check["other_names"]):
            db.add(Conclusion(run_id=run.id, evaluation_subject_id=sid, text=text, status="draft", origin="ai",
                              original_text=text))
        elif text:
            dropped.append({"subject": name, "statement": text, "reason": "Conclusion names a person other than the subject."})
        db.flush()

    overall = _overall(db, run, call)
    if overall:
        calls += 1
    run.results = {**run.results, "ai": {"calls": calls, "kept": kept, "dropped": dropped,
                                         "overall_conclusion": bool(overall)}}
    db.flush()
    return run.results["ai"]


def overall_context(db: Session, run: AnalysisRun) -> Dict[str, Any]:
    """Subjects described by role, each with its draft and accepted findings (never rejected ones)."""
    ev = db.get(Evaluation, run.evaluation_id)
    names = people_names(db, ev)
    out = []
    for sid in run.results["order"]:
        res = run.results["subjects"][sid]
        fs = [f for f in an.findings(db, run, sid) if f.status != "rejected"]
        if not fs:
            continue
        label = res["name"] if res["kind"] in ("board", "committee", "secretariat") else ROLE_WORDS.get(res["type"], "a director")
        out.append({"subject": label, "findings": [{"kind": f.kind, "support": f.support,
                                                     "statement": scrub(f.statement, names)} for f in fs]})
    return {"SUBJECTS": out}


def _overall(db: Session, run: AnalysisRun, call: LLMCall) -> Optional[Conclusion]:
    context = overall_context(db, run)
    if not context["SUBJECTS"]:
        return None
    try:
        reply = OverallDraft.model_validate(_parse(call(OVERALL_SYSTEM_PROMPT, overall_user_prompt(context))))
    except (ValueError, ValidationError):
        return None
    names = people_names(db, db.get(Evaluation, run.evaluation_id))
    if mentions(reply.conclusion, names):
        return None
    c = Conclusion(run_id=run.id, evaluation_subject_id=None, text=reply.conclusion.strip(), status="draft",
                   origin="ai", original_text=reply.conclusion.strip())
    db.add(c)
    db.flush()
    return c

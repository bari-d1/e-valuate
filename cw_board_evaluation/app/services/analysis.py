"""
app.services.analysis
---------------------
Analysis of an assembled evaluation: from every director's one form to results
and draft findings per subject (the board, each committee, each director, the
secretariat). Thresholds and rules live in app.domain.analysis_rules.

A run:
1. gathers the evidence register: one AnalysisEvidence row per answer used
   (submitted forms only, unless include_unsubmitted), about subjects in the
   evaluation's scope, with the respondent's category and a per-run pseudonym;
2. computes results per subject (themes, items, rater-group splits, self versus
   peer, yes/no and choice counts, facts and compliance checks, comments,
   completion), suppressing small groups, and stores them on the run;
3. drafts computed findings, each linked to the evidence rows behind it (and
   to clauses for compliance and clause-linked items);
4. optionally asks AI for more drafts (app.services.analysis_ai).
After that the run's evidence and results never change: a re-run is a new run.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisEvidence,
    AnalysisRun,
    AssessmentAssignment,
    BoardMember,
    Conclusion,
    Evaluation,
    EvaluationContextSnapshot,
    EvaluationScopeSubjectType,
    EvaluationSubject,
    Finding,
    FindingClause,
    FindingEvidence,
    GovernanceClause,
    OrganisationFact,
    Participant,
    Question,
    QuestionBankItem,
    QuestionBankItemClause,
    Response,
    Theme,
)
from app.domain import analysis_rules as R
from app.domain.board_member_profile import GENERATION_ONLY_KEYS, PROFILE_FACTS_BY_KEY, governance_role_from_participant_role
from app.domain.org_profile import FACTS_BY_KEY
from app.domain.question_rules import format_fact_value
from app.services import participant_portal as form
from app.services.question_selection import ROLE_LABELS

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=30)
INDIVIDUAL_TYPES = ("CHAIR", "MD_CEO", "ED", "NED", "INED")
SUBJECT_ORDER = ("BOARD", "COMMITTEE", "CHAIR", "MD_CEO", "ED", "NED", "INED", "COMPANY_SECRETARY")


class AnalysisError(ValueError):
    """An analysis action that isn't allowed now. The message is safe to show the consultant."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ----------------------------
# Small helpers
# ----------------------------

def subject_name(s: EvaluationSubject) -> str:
    """How a subject is named in results and findings: without the internal display code."""
    return s.label.split(" · ")[-1]


def subject_kind(s: EvaluationSubject) -> str:
    return {"BOARD": "board", "COMMITTEE": "committee", "COMPANY_SECRETARY": "secretariat"}.get(
        s.subject_type_code, "person")


def is_individual(s: EvaluationSubject) -> bool:
    return s.subject_type_code in INDIVIDUAL_TYPES


def category_of(p: Participant) -> str:
    return R.CATEGORY_FOR_ROLE.get(governance_role_from_participant_role(p.role) or "", "other")


def clause_label(c: GovernanceClause) -> str:
    return f"{c.code.replace('_', ' ')} {c.reference}"


def clause_dict(c: GovernanceClause) -> Dict[str, Any]:
    return {"clause_id": str(c.id), "label": clause_label(c), "heading": c.heading, "text": c.text}


def category_label(run: AnalysisRun, e: AnalysisEvidence) -> str:
    """
    The respondent's category as shown next to an answer. Facts keep their role (a fact is
    attributed to whoever is responsible for it). Opinions show the category only when at least
    min_raters respondents in the run share it, so a category of one or two never points at a person.
    """
    if e.is_self:
        return R.CATEGORY_LABELS["self"]
    if _is_fact(e):
        return R.CATEGORY_LABELS.get(e.respondent_category, "Respondent")
    counts: Dict[str, int] = defaultdict(int)
    for p in (run.inputs or {}).get("participants", []):
        counts[p["category"]] += 1
    if counts.get(e.respondent_category, 0) >= run.settings.get("min_raters", R.DEFAULT_MIN_RATERS):
        return R.CATEGORY_LABELS.get(e.respondent_category, "Respondent")
    return "Director"


def value_text(v: Dict[str, Any]) -> str:
    if "score" in v:
        return str(v["score"])
    if v.get("dont_know"):
        return "Don't know"
    if "answer" in v:
        return "Yes" if v["answer"] == "yes" else "No"
    if "choice" in v:
        return v["choice"]
    if "choices" in v:
        return "; ".join(v["choices"])
    if "confirm" in v:
        return "Confirmed as correct" if v["confirm"] == "correct" else (
            f"Needs updating: {v['correction']}" if v.get("correction") else "Needs updating")
    return v.get("text") or ""


def _value(q: Question, r: Response) -> Optional[Dict[str, Any]]:
    """An answer as stored evidence, or None if it's empty."""
    v = form.answer_value(r, q)
    if q.section == "confirm":
        return {"confirm": v["status"], "correction": v.get("correction") or None} if v and v.get("status") else None
    if v is None or v == "" or v == []:
        return None
    if q.answer_type == "rating":
        return {"dont_know": True} if v == "dont_know" else {"score": int(v)}
    if q.answer_type == "yesno":
        return {"answer": v}
    if q.answer_type == "single_select":
        return {"choice": v}
    if q.answer_type == "multi_select":
        return {"choices": list(v)}
    return {"text": str(v).strip()} if str(v).strip() else None


# ----------------------------
# Starting and running
# ----------------------------

def start_run(db: Session, ev: Evaluation, by: str, *, min_raters: Optional[int] = None,
              include_unsubmitted: bool = False, ai: bool = False) -> AnalysisRun:
    if not form.uses_assembled_sets(db, ev.id):
        raise AnalysisError("This evaluation uses the older questionnaire; see the Report page.")
    n = R.DEFAULT_MIN_RATERS if min_raters is None else int(min_raters)
    if not 2 <= n <= 10:
        raise AnalysisError("Minimum raters must be between 2 and 10.")
    running = db.execute(select(AnalysisRun).where(AnalysisRun.evaluation_id == ev.id,
                                                   AnalysisRun.status == "running")).scalars().first()
    if running is not None and running.created_at < _now() - STALE_AFTER:
        # A run that never finished (e.g. the server restarted, or an AI call hung) mustn't block new ones
        running.status, running.finished_at = "failed", _now()
        running.error = "Stopped: it didn't finish within 30 minutes."
        running = None
    if running is not None:
        raise AnalysisError("An analysis is already running for this evaluation.")
    run = AnalysisRun(evaluation_id=ev.id, status="running", created_by=by or "consultant",
                      settings={"min_raters": n, "include_unsubmitted": bool(include_unsubmitted),
                                "ai_requested": bool(ai), "ai_used": False}, inputs={}, results={})
    db.add(run)
    db.flush()
    return run


def session_factory():
    """Session for background runs. Tests replace this to use their transaction."""
    from app.db.session import SessionLocal

    return SessionLocal()


def execute_run(run_id, llm_call=None) -> None:
    """Background entry point: run the analysis in its own session and record the outcome."""
    db = session_factory()
    try:
        run = db.get(AnalysisRun, run_id)
        if run is None:
            return
        try:
            execute(db, run, llm_call=llm_call)
            db.commit()
        except Exception as e:  # recorded on the run for the consultant
            log.exception("Analysis run %s failed", run_id)
            db.rollback()
            run = db.get(AnalysisRun, run_id)
            run.status, run.error, run.finished_at = "failed", str(e)[:2000], _now()
            db.commit()
    finally:
        db.close()


def execute(db: Session, run: AnalysisRun, *, llm_call=None) -> AnalysisRun:
    if run.status != "running":
        raise AnalysisError("This run has finished; its evidence and results can't change. Start a new run.")
    ev = db.get(Evaluation, run.evaluation_id)
    evidence, ctx = gather_evidence(db, ev, run)
    run.results = compute_results(db, ev, run, evidence, ctx)
    draft_computed_findings(db, run, evidence, ctx)
    if run.settings.get("ai_requested"):
        from app.services import analysis_ai  # AI drafting is optional and imported lazily
        if analysis_ai.enabled():
            analysis_ai.draft(db, run, llm_call=llm_call)
            run.settings = {**run.settings, "ai_used": True}
    run.status, run.finished_at = "done", _now()
    db.flush()
    return run


# ----------------------------
# 1. The evidence register
# ----------------------------

def scoped_subjects(db: Session, ev: Evaluation) -> List[EvaluationSubject]:
    scope = set(db.execute(select(EvaluationScopeSubjectType.subject_type_code).where(
        EvaluationScopeSubjectType.evaluation_id == ev.id)).scalars())
    rows = db.execute(select(EvaluationSubject).where(EvaluationSubject.evaluation_id == ev.id)).scalars().all()
    rows = [s for s in rows if not scope or s.subject_type_code in scope]
    return sorted(rows, key=lambda s: (SUBJECT_ORDER.index(s.subject_type_code)
                                       if s.subject_type_code in SUBJECT_ORDER else 99, s.label))


def gather_evidence(db: Session, ev: Evaluation, run: AnalysisRun) -> Tuple[List[AnalysisEvidence], Dict[str, Any]]:
    include_unsubmitted = run.settings.get("include_unsubmitted", False)
    subjects = {s.id: s for s in scoped_subjects(db, ev)}
    participants = {p.id: p for p in db.execute(select(Participant).where(Participant.evaluation_id == ev.id)).scalars()}
    assignments = {a.respondent_participant_id: a for a in db.execute(select(AssessmentAssignment).where(
        AssessmentAssignment.evaluation_id == ev.id, AssessmentAssignment.assignment_type == form.ASSEMBLED)).scalars()}
    used = {pid: a for pid, a in assignments.items()
            if a.submitted_at or (include_unsubmitted and a.last_activity_at)}
    questions = {q.id: q for q in db.execute(select(Question).where(
        Question.evaluation_id == ev.id, Question.participant_id.is_not(None),
        Question.status.in_(("approved", "locked")))).scalars()}
    items = {i.id: i for i in db.execute(select(QuestionBankItem).where(
        QuestionBankItem.id.in_({q.bank_item_id for q in questions.values() if q.bank_item_id}))).scalars()}
    responses = db.execute(select(Response).where(
        Response.assignment_id.in_([a.id for a in used.values()]))).scalars().all() if used else []
    # Pseudonyms in a fixed order that says nothing about who is who
    refs = {pid: f"R{n}" for n, pid in enumerate(sorted(used, key=str), start=1)}

    rows: List[AnalysisEvidence] = []
    for r in sorted(responses, key=lambda r: (str(r.participant_id), str(r.question_id))):
        q = questions.get(r.question_id)
        if q is None or q.evaluation_subject_id not in subjects:
            continue
        value = _value(q, r)
        if value is None:
            continue
        p = participants[r.participant_id]
        s = subjects[q.evaluation_subject_id]
        item = items.get(q.bank_item_id)
        e = AnalysisEvidence(
            run_id=run.id, response_id=r.id, question_id=q.id, evaluation_subject_id=s.id, theme_code=q.theme_code,
            evidence_source_code=q.evidence_source_code, bank_item_code=item.code if item else None,
            answer_type="confirm" if q.section == "confirm" else q.answer_type, question_text=q.text,
            respondent_category=category_of(p), respondent_ref=refs[p.id],
            is_self=bool(s.participant_id and s.participant_id == p.id and is_individual(s)),
            in_progress=not used[p.id].submitted_at, value=value,
        )
        db.add(e)
        rows.append(e)
    db.flush()

    snapshot = db.execute(select(EvaluationContextSnapshot).where(EvaluationContextSnapshot.evaluation_id == ev.id)
                          .order_by(EvaluationContextSnapshot.created_at.desc()).limit(1)).scalars().first()
    run.inputs = {
        "participants": [{"participant_id": str(pid), "category": category_of(participants[pid]),
                          "submitted_at": _iso(a.submitted_at), "in_progress": not a.submitted_at}
                         for pid, a in sorted(used.items(), key=lambda x: str(x[0]))],
        "not_included": sorted(str(pid) for pid in participants if pid not in used),
        "bank_items": {i.code: i.version for i in items.values()},
        "snapshot_id": str(snapshot.id) if snapshot else None,
        "evidence_rows": len(rows),
    }
    eligible: Dict[Any, set] = defaultdict(set)  # subject -> participants whose form asks about it
    for q in questions.values():
        if q.evaluation_subject_id in subjects:
            eligible[q.evaluation_subject_id].add(q.participant_id)
    clauses: Dict[str, List[GovernanceClause]] = defaultdict(list)
    for link, c in db.execute(select(QuestionBankItemClause, GovernanceClause)
                              .join(GovernanceClause, GovernanceClause.id == QuestionBankItemClause.clause_id)
                              .where(QuestionBankItemClause.item_id.in_(list(items)))).all():
        clauses[items[link.item_id].code].append(c)
    ctx = {
        "subjects": subjects, "eligible": eligible, "clauses": clauses,
        "expected": {i.code: i.expected_answer for i in items.values() if i.expected_answer},
        "themes": {t.code: t.name for t in db.execute(select(Theme)).scalars()},
        "min_raters": run.settings["min_raters"], "participants": participants, "evaluation": ev,
    }
    return rows, ctx


# ----------------------------
# 2 and 3. Results
# ----------------------------

def _opinions(rows: List[AnalysisEvidence]) -> List[AnalysisEvidence]:
    """Ratings that count towards scores: PERCEPTION ratings by people other than the subject."""
    return [e for e in rows if e.answer_type == "rating" and e.evidence_source_code == "PERCEPTION"
            and not e.is_self and "score" in e.value]


def _is_fact(e: AnalysisEvidence) -> bool:
    return e.evidence_source_code == "ORG_FACT" or e.answer_type == "confirm" or (
        e.evidence_source_code == "ROLE_SELF" and e.answer_type != "rating")


def _people(rows: List[AnalysisEvidence]) -> int:
    return len({e.respondent_ref for e in rows})


def _rating_block(rows: List[AnalysisEvidence], *, by_rater: bool) -> Dict[str, Any]:
    """n raters, mean, distribution, spread and consensus. by_rater: spread and consensus over each rater's average."""
    scores = [e.value["score"] for e in rows]
    per: Dict[str, List[int]] = defaultdict(list)
    for e in rows:
        per[e.respondent_ref].append(e.value["score"])
    basis = [sum(v) / len(v) for v in per.values()] if by_rater else scores
    return {"raters": len(per), "ratings": len(scores), "mean": R.mean(scores), "distribution": R.distribution(scores),
            "spread": R.spread(basis), "consensus": R.consensus(basis),
            "dont_know": 0}


def _suppress(individual: bool, people: int, n: int) -> Optional[str]:
    if individual and people < n:
        return (f"Only {people} {'person' if people == 1 else 'people'} rated this; results about an individual "
                f"need at least {n}.")
    return None


def _split(rows: List[AnalysisEvidence], n: int) -> Optional[Dict[str, Any]]:
    """Executives versus non-executives, only when every group shown has at least n people."""
    groups = {}
    for key, (label, cats) in R.SPLIT_GROUPS.items():
        g = [e for e in rows if e.respondent_category in cats]
        if g:
            groups[key] = (label, g)
    if len(groups) < 2:
        return None
    small = [f"{label}: {_people(g)} {'person' if _people(g) == 1 else 'people'}" for label, g in groups.values()
             if _people(g) < n]
    if small:
        return {"suppressed": f"Not shown: {', '.join(small)} (each group needs at least {n})."}
    return {"groups": [{"key": k, "label": label, "raters": _people(g), "mean": R.mean([e.value["score"] for e in g])}
                       for k, (label, g) in groups.items()]}


def _confirmed_facts(db: Session, ev: Evaluation, s: EvaluationSubject) -> List[Dict[str, Any]]:
    """Confirmed profile facts for the board (organisation) or a director (never generation-only notes)."""
    out = []
    if s.subject_type_code == "BOARD" and ev.organisation_id:
        for f in db.execute(select(OrganisationFact).where(OrganisationFact.organisation_id == ev.organisation_id,
                                                           OrganisationFact.status == "confirmed")).scalars():
            spec = FACTS_BY_KEY.get(f.key, {})
            out.append({"label": spec.get("label", f.key.replace("_", " ").capitalize()),
                        "value": format_fact_value(f.value), "source": "Confirmed company profile"})
    elif is_individual(s) and s.participant_id:
        p = db.get(Participant, s.participant_id)
        m = db.get(BoardMember, p.board_member_id) if p and p.board_member_id else None
        if m is not None:
            from app.services.board_members import confirmed_facts
            for key, f in confirmed_facts(db, m).items():
                if key in GENERATION_ONLY_KEYS:
                    continue
                spec = PROFILE_FACTS_BY_KEY.get(key, {})
                value = ROLE_LABELS.get(f.value, format_fact_value(f.value)) if key == "governance_role" \
                    else format_fact_value(f.value)
                out.append({"label": spec.get("label", key.replace("_", " ").capitalize()),
                            "value": value, "source": "Confirmed director profile"})
    return sorted(out, key=lambda x: x["label"])


def compute_results(db: Session, ev: Evaluation, run: AnalysisRun, evidence: List[AnalysisEvidence],
                    ctx: Dict[str, Any]) -> Dict[str, Any]:
    n = ctx["min_raters"]
    by_subject: Dict[Any, List[AnalysisEvidence]] = defaultdict(list)
    for e in evidence:
        by_subject[e.evaluation_subject_id].append(e)
    subjects_out: Dict[str, Any] = {}
    order: List[str] = []
    for s in ctx["subjects"].values():
        rows = by_subject.get(s.id, [])
        individual = is_individual(s)
        respondents = {e.respondent_ref for e in rows if not e.is_self}
        opinions = _opinions(rows)
        out: Dict[str, Any] = {
            "subject_id": str(s.id), "name": subject_name(s), "type": s.subject_type_code, "kind": subject_kind(s),
            "individual": individual,
            "completion": {"eligible": len(ctx["eligible"].get(s.id, set())), "answered": _people(rows)},
            "raters": len(respondents),
            "small_sample": (not individual) and 0 < len(respondents) < n,
            "suppressed": [], "themes": {}, "self_peer": [], "choices": [], "facts": [], "comments": {},
            "comments_suppressed": None, "in_progress_included": any(e.in_progress for e in rows),
        }
        # Themes and items
        themes: Dict[str, List[AnalysisEvidence]] = defaultdict(list)
        for e in opinions:
            themes[e.theme_code or "GENERAL"].append(e)
        for code, trows in sorted(themes.items()):
            block = _rating_block(trows, by_rater=True)
            reason = _suppress(individual, block["raters"], n)
            t = {"theme_code": code, "label": ctx["themes"].get(code, code), **block, "suppressed": reason,
                 "items": [], "split": None}
            if reason:
                t.update(mean=None, distribution=None, spread=None, consensus=None)
                out["suppressed"].append({"what": t["label"], "reason": reason})
            items: Dict[str, List[AnalysisEvidence]] = defaultdict(list)
            for e in trows:
                items[e.bank_item_code or e.question_text].append(e)
            for code_i, irows in sorted(items.items()):
                ib = _rating_block(irows, by_rater=False)
                ireason = _suppress(individual, ib["raters"], n)
                t["items"].append({
                    "code": code_i, "question": irows[0].question_text, **ib,
                    "clauses": [clause_dict(c) for c in ctx["clauses"].get(code_i, [])], "suppressed": ireason,
                    **({"mean": None, "distribution": None, "spread": None, "consensus": None} if ireason else {}),
                })
            if not reason:
                t["split"] = _split(trows, n)
            out["themes"][code] = t
        # Self versus peer on the core statements (individual directors)
        if individual:
            for k in range(1, 7):
                peer = [e for e in opinions if e.bank_item_code == f"{R.PEER_PREFIX}{k:02d}"]
                own = [e for e in rows if e.is_self and e.bank_item_code == f"{R.SELF_PREFIX}{k:02d}" and "score" in e.value]
                if not peer and not own:
                    continue
                pm = R.mean([e.value["score"] for e in peer])
                reason = _suppress(True, _people(peer), n)
                self_score = own[0].value["score"] if own else None
                gap = round(self_score - pm, 2) if (self_score is not None and pm is not None and not reason) else None
                out["self_peer"].append({
                    "statement": peer[0].question_text if peer else own[0].question_text, "code": f"CORE-{k:02d}",
                    "peer_mean": None if reason else pm, "peer_raters": _people(peer), "self": self_score,
                    "gap": gap, "flagged": gap is not None and abs(gap) >= R.SELF_PEER_GAP, "suppressed": reason,
                })
        # Yes/no and choice opinions
        choice_rows: Dict[str, List[AnalysisEvidence]] = defaultdict(list)
        for e in rows:
            if e.answer_type in ("yesno", "single_select", "multi_select") and not _is_fact(e) and not e.is_self:
                choice_rows[e.bank_item_code or e.question_text].append(e)
        for code_c, crows in sorted(choice_rows.items()):
            counts: Dict[str, int] = defaultdict(int)
            for e in crows:
                for v in (e.value.get("choices") or [value_text(e.value)]):
                    counts[v] += 1
            people = _people(crows)
            reason = _suppress(individual, people, n)
            out["choices"].append({
                "code": code_c, "question": crows[0].question_text, "type": crows[0].answer_type, "respondents": people,
                "counts": None if reason else dict(counts),
                "percentages": None if reason else {k: round(100 * v / people) for k, v in counts.items()},
                "suppressed": reason,
            })
        # Facts and compliance checks (never averaged)
        facts: Dict[str, List[AnalysisEvidence]] = defaultdict(list)
        for e in rows:
            if _is_fact(e):
                facts[e.bank_item_code or e.question_text].append(e)
        for code_f, frows in sorted(facts.items()):
            expected = ctx["expected"].get(code_f)
            cls = ctx["clauses"].get(code_f, [])
            answers = [{"category": category_label(run, e),
                        "value": value_text(e.value), "evidence_id": str(e.id)} for e in frows]
            check = None
            if expected and cls and frows[0].answer_type == "yesno" and frows[0].evidence_source_code in ("ORG_FACT", "ROLE_SELF"):
                given = [e.value.get("answer") for e in frows]
                check = {"expected": "Yes" if expected == "yes" else "No", "met": all(g == expected for g in given),
                         "agree": len(set(given)) == 1}
            out["facts"].append({"code": code_f, "question": frows[0].question_text, "answers": answers,
                                 "clauses": [clause_dict(c) for c in cls], "check": check})
        out["profile_facts"] = _confirmed_facts(db, ev, s)
        # Comments grouped by theme, only where the group is big enough
        comment_rows = [e for e in rows if e.answer_type == "comment" and not _is_fact(e)]
        if comment_rows and individual and len(respondents) < n:
            out["comments_suppressed"] = (f"Comments hidden: only {len(respondents)} people answered about "
                                          f"{subject_name(s)}; at least {n} are needed.")
            comment_rows = [e for e in comment_rows if e.is_self]
        for e in comment_rows:
            out["comments"].setdefault(e.theme_code or "GENERAL", []).append({
                "evidence_id": str(e.id), "category": category_label(run, e),
                "question": e.question_text, "text": e.value.get("text")})
        if out["small_sample"]:
            out["notice"] = (f"Small sample: {len(respondents)} {'person' if len(respondents) == 1 else 'people'} "
                             f"answered about {subject_name(s)} (fewer than {n}). Read these results with care.")
        subjects_out[str(s.id)] = out
        order.append(str(s.id))
    return {
        "generated_at": _now().isoformat(), "min_raters": n,
        "include_unsubmitted": run.settings.get("include_unsubmitted", False),
        "respondents": {"included": len(run.inputs["participants"]),
                        "in_progress": sum(1 for p in run.inputs["participants"] if p["in_progress"]),
                        "not_included": len(run.inputs["not_included"])},
        "order": order, "subjects": subjects_out,
    }


# ----------------------------
# 4. Computed findings
# ----------------------------

def _finding(db: Session, run: AnalysisRun, s_id, kind: str, statement: str, support: str, rule: str,
             evidence: List[AnalysisEvidence], *, theme: Optional[str] = None, item: Optional[str] = None,
             clauses: Optional[List[Dict[str, Any]]] = None, origin: str = "computed") -> Finding:
    f = Finding(run_id=run.id, evaluation_subject_id=s_id, theme_code=theme, bank_item_code=item, kind=kind,
                statement=statement, support=support, origin=origin, status="draft", original_text=statement, rule=rule)
    db.add(f)
    db.flush()
    for eid in {e.id for e in evidence}:
        db.add(FindingEvidence(finding_id=f.id, evidence_id=eid))
    for c in clauses or []:
        db.add(FindingClause(finding_id=f.id, clause_id=c["clause_id"]))
    db.flush()
    return f


def _avg(x: Optional[float]) -> str:
    return f"{x:.1f}"


def draft_computed_findings(db: Session, run: AnalysisRun, evidence: List[AnalysisEvidence], ctx: Dict[str, Any]) -> None:
    by_subject: Dict[str, List[AnalysisEvidence]] = defaultdict(list)
    for e in evidence:
        by_subject[str(e.evaluation_subject_id)].append(e)
    for sid, res in run.results["subjects"].items():
        rows = by_subject.get(sid, [])
        name = res["name"]
        opinions = _opinions(rows)
        for code, t in res["themes"].items():
            if t["suppressed"]:
                continue
            trows = [e for e in opinions if (e.theme_code or "GENERAL") == code]
            label = t["label"].lower()
            facts = f"average {_avg(t['mean'])} from {t['raters']} rater{'' if t['raters'] == 1 else 's'}"
            theme_kind = None
            if t["consensus"] == "divided":
                split = t.get("split") or {}
                extra = ""
                if split.get("groups"):
                    extra = " " + "; ".join(f"{g['label']} average {_avg(g['mean'])}" for g in split["groups"]) + "."
                _finding(db, run, sid, "observation",
                         f"Views on {label} for {name} are divided ({facts}, ranging from "
                         f"{min(e.value['score'] for e in trows)} to {max(e.value['score'] for e in trows)}).{extra}",
                         "conflicting", "theme_divided", trows, theme=code)
            elif t["mean"] >= R.THEME_STRENGTH_MEAN and t["consensus"] == "strong agreement":
                theme_kind = "strength"
                _finding(db, run, sid, "strength", f"{name} is rated well on {label} ({facts}, with strong agreement).",
                         R.support_for(t["raters"], t["consensus"]), "theme_strength", trows, theme=code)
            elif t["mean"] <= R.CONCERN_MEAN:
                theme_kind = "concern"
                low = [it for it in t["items"] if not it["suppressed"] and it["mean"] is not None
                       and it["mean"] <= R.CONCERN_MEAN]
                cited = [c for it in low for c in it["clauses"]]
                detail = "; ".join(
                    f"\"{it['question']}\" {_avg(it['mean'])}" + (f" ({', '.join(c['label'] for c in it['clauses'])})"
                                                               if it["clauses"] else "") for it in low[:3])
                _finding(db, run, sid, "concern",
                         f"{name} is rated poorly on {label} ({facts})." + (f" Lowest: {detail}." if detail else ""),
                         R.support_for(t["raters"], t["consensus"]), "theme_concern", trows, theme=code,
                         clauses=list({c["clause_id"]: c for c in cited}.values()))
            for it in t["items"]:
                if it["suppressed"] or not it["clauses"] or it["raters"] < 1:
                    continue
                irows = [e for e in trows if (e.bank_item_code or e.question_text) == it["code"]]
                ifacts = f"average {_avg(it['mean'])} from {it['raters']} rater{'' if it['raters'] == 1 else 's'}"
                refs = ", ".join(c["label"] for c in it["clauses"])
                if it["mean"] <= R.CONCERN_MEAN and theme_kind != "concern":
                    _finding(db, run, sid, "concern", f"\"{it['question']}\" scores low for {name} ({ifacts}); see {refs}.",
                             R.support_for(it["raters"], it["consensus"]), "item_concern", irows, theme=code,
                             item=it["code"], clauses=it["clauses"])
                elif (it["mean"] >= R.ITEM_STRENGTH_MEAN and it["consensus"] == "strong agreement"
                      and theme_kind != "strength"):
                    _finding(db, run, sid, "strength", f"\"{it['question']}\" scores high for {name} ({ifacts}); see {refs}.",
                             R.support_for(it["raters"], it["consensus"]), "item_strength", irows, theme=code,
                             item=it["code"], clauses=it["clauses"])
        for sp in res["self_peer"]:
            if not sp["flagged"]:
                continue
            k = sp["code"].split("-")[-1]
            srows = [e for e in rows if e.bank_item_code in (f"{R.PEER_PREFIX}{k}", f"{R.SELF_PREFIX}{k}")
                     and "score" in e.value and (e.is_self or e.evidence_source_code == "PERCEPTION")]
            way = "higher" if sp["gap"] > 0 else "lower"
            _finding(db, run, sid, "self_perception_gap",
                     f"{name} rates themselves {sp['self']} on \"{sp['statement']}\", {abs(sp['gap']):.1f} {way} than "
                     f"colleagues' average of {_avg(sp['peer_mean'])} ({sp['peer_raters']} raters).",
                     R.support_for(sp["peer_raters"]), "self_peer_gap", srows,
                     theme=srows[0].theme_code if srows else None, item=f"{R.PEER_PREFIX}{k}")
        for fact in res["facts"]:
            check = fact["check"]
            if not check or check["met"]:
                continue
            frows = [e for e in rows if (e.bank_item_code or e.question_text) == fact["code"]]
            who = "; ".join(sorted({a["category"] for a in fact["answers"]}))
            given = ", ".join(sorted({a["value"] for a in fact["answers"]}))
            refs = ", ".join(c["label"] for c in fact["clauses"])
            _finding(db, run, sid, "compliance_gap",
                     f"Answered \"{given}\" to \"{fact['question']}\" ({who}); good practice expects "
                     f"\"{check['expected']}\" under {refs}.",
                     R.FACT_SUPPORT if check["agree"] else "conflicting", "compliance_shortfall", frows,
                     theme=frows[0].theme_code if frows else None, item=fact["code"], clauses=fact["clauses"])


# ----------------------------
# Reading runs
# ----------------------------

def latest_run(db: Session, ev_id: str) -> Optional[AnalysisRun]:
    return db.execute(select(AnalysisRun).where(AnalysisRun.evaluation_id == ev_id)
                      .order_by(AnalysisRun.created_at.desc()).limit(1)).scalars().first()


def run_dict(run: AnalysisRun) -> Dict[str, Any]:
    return {"run_id": str(run.id), "status": run.status, "settings": run.settings, "error": run.error,
            "created_by": run.created_by, "created_at": _iso(run.created_at), "finished_at": _iso(run.finished_at),
            "completed_by": run.completed_by, "completed_at": _iso(run.completed_at),
            "respondents": (run.results or {}).get("respondents"), "evidence_rows": (run.inputs or {}).get("evidence_rows")}


def evidence_dict(e: AnalysisEvidence, run: AnalysisRun) -> Dict[str, Any]:
    """An answer for display: never who gave it, only their category."""
    return {"evidence_id": str(e.id), "question": e.question_text, "theme_code": e.theme_code,
            "answer_type": e.answer_type, "category": category_label(run, e),
            "respondent": e.respondent_ref, "value": value_text(e.value), "in_progress": e.in_progress,
            "fact": _is_fact(e)}


def subject_evidence(db: Session, run: AnalysisRun, subject_id) -> List[AnalysisEvidence]:
    return list(db.execute(select(AnalysisEvidence).where(AnalysisEvidence.run_id == run.id,
                                                         AnalysisEvidence.evaluation_subject_id == subject_id)
                           .order_by(AnalysisEvidence.theme_code, AnalysisEvidence.bank_item_code,
                                     AnalysisEvidence.respondent_ref)).scalars().all())


def finding_dict(db: Session, f: Finding) -> Dict[str, Any]:
    ev_ids = [str(x) for x in db.execute(select(FindingEvidence.evidence_id).where(FindingEvidence.finding_id == f.id)).scalars()]
    cls = db.execute(select(GovernanceClause).join(FindingClause, FindingClause.clause_id == GovernanceClause.id)
                     .where(FindingClause.finding_id == f.id)).scalars().all()
    return {"finding_id": str(f.id), "subject_id": str(f.evaluation_subject_id) if f.evaluation_subject_id else None,
            "theme_code": f.theme_code, "kind": f.kind, "statement": f.statement, "support": f.support,
            "origin": f.origin, "status": f.status, "original_text": f.original_text,
            "edited_by": f.edited_by, "edited_at": _iso(f.edited_at), "evidence_ids": ev_ids,
            "evidence_count": len(ev_ids), "clauses": [clause_dict(c) for c in cls]}


def findings(db: Session, run: AnalysisRun, subject_id=None) -> List[Finding]:
    stmt = select(Finding).where(Finding.run_id == run.id)
    if subject_id is not None:
        stmt = stmt.where(Finding.evaluation_subject_id == subject_id)
    return list(db.execute(stmt.order_by(Finding.created_at, Finding.id)).scalars().all())


def conclusions(db: Session, run: AnalysisRun) -> List[Conclusion]:
    return list(db.execute(select(Conclusion).where(Conclusion.run_id == run.id)).scalars().all())


def conclusion_dict(c: Conclusion) -> Dict[str, Any]:
    return {"conclusion_id": str(c.id), "subject_id": str(c.evaluation_subject_id) if c.evaluation_subject_id else None,
            "text": c.text, "status": c.status, "origin": c.origin, "original_text": c.original_text,
            "no_findings": c.no_findings, "edited_by": c.edited_by, "edited_at": _iso(c.edited_at)}


# ----------------------------
# The consultant's decisions
# ----------------------------

def _require_done(run: AnalysisRun) -> None:
    if run.status != "done":
        raise AnalysisError("The analysis hasn't finished yet.")
    if run.completed_at:
        raise AnalysisError("The analysis is marked complete. Start a new run to change findings.")


def add_finding(db: Session, run: AnalysisRun, by: str, *, subject_id, kind: str, statement: str, support: str,
                theme_code: Optional[str] = None, evidence_ids: Optional[List[str]] = None,
                clause_ids: Optional[List[str]] = None) -> Finding:
    _require_done(run)
    if kind not in ("strength", "concern", "observation", "compliance_gap", "self_perception_gap"):
        raise ValueError("Choose a kind of finding.")
    if support not in ("strong", "moderate", "limited", "conflicting"):
        raise ValueError("Choose a support level.")
    if not (statement or "").strip():
        raise ValueError("Write the finding.")
    if subject_id is not None and str(subject_id) not in run.results["subjects"]:
        raise ValueError("That subject isn't part of this analysis.")
    rows = []
    if evidence_ids:
        try:
            evidence_ids = [uuid.UUID(str(x)) for x in evidence_ids]
        except ValueError as e:
            raise ValueError("Some of the evidence isn't from this analysis.") from e
        rows = db.execute(select(AnalysisEvidence).where(AnalysisEvidence.run_id == run.id,
                                                         AnalysisEvidence.id.in_(evidence_ids))).scalars().all()
        if len(rows) != len(set(evidence_ids)):
            raise ValueError("Some of the evidence isn't from this analysis.")
    f = Finding(run_id=run.id, evaluation_subject_id=subject_id, theme_code=theme_code, kind=kind,
                statement=statement.strip(), support=support, origin="consultant", status="accepted",
                edited_by=by, edited_at=_now())
    db.add(f)
    db.flush()
    for e in rows:
        db.add(FindingEvidence(finding_id=f.id, evidence_id=e.id))
    for cid in clause_ids or []:
        db.add(FindingClause(finding_id=f.id, clause_id=cid))
    db.flush()
    return f


def update_finding(db: Session, run: AnalysisRun, f: Finding, by: str, *, status: Optional[str] = None,
                   statement: Optional[str] = None, support: Optional[str] = None, kind: Optional[str] = None) -> Finding:
    """Accept, reject, or edit (which keeps the original draft text)."""
    _require_done(run)
    if statement is not None:
        if not statement.strip():
            raise ValueError("A finding can't be empty.")
        if statement.strip() != f.statement:
            f.statement = statement.strip()
            f.status = "edited" if f.origin != "consultant" else "accepted"
    if support is not None:
        if support not in ("strong", "moderate", "limited", "conflicting"):
            raise ValueError("Choose a support level.")
        f.support = support
    if kind is not None:
        f.kind = kind
    if status is not None:
        if status not in ("accepted", "rejected", "draft"):
            raise ValueError("Status must be accepted, rejected or draft.")
        f.status = status
    f.edited_by, f.edited_at = by, _now()
    db.flush()
    return f


def set_conclusion(db: Session, run: AnalysisRun, by: str, *, subject_id, text: Optional[str] = None,
                   status: Optional[str] = None, no_findings: Optional[bool] = None) -> Conclusion:
    _require_done(run)
    if subject_id is not None and str(subject_id) not in run.results["subjects"]:
        raise ValueError("That subject isn't part of this analysis.")
    c = db.execute(select(Conclusion).where(Conclusion.run_id == run.id, Conclusion.evaluation_subject_id == subject_id)
                   if subject_id is not None else
                   select(Conclusion).where(Conclusion.run_id == run.id, Conclusion.evaluation_subject_id.is_(None))
                   ).scalars().first()
    if status is not None and status not in ("accepted", "rejected", "draft"):
        raise ValueError("Status must be accepted, rejected or draft.")
    new_text = text.strip() if text is not None else (c.text if c else "")
    new_none = bool(no_findings) if no_findings is not None else (c.no_findings if c else False)
    if status == "accepted" and not new_text and not new_none:
        raise ValueError("Write the conclusion before accepting it.")
    if c is None:
        c = Conclusion(run_id=run.id, evaluation_subject_id=subject_id, text="", status="draft", origin="consultant")
        db.add(c)
    if text is not None:
        if c.origin != "consultant" and text.strip() != c.text and c.original_text is None:
            c.original_text = c.text
        c.text = text.strip()
        if c.origin != "consultant":
            c.status = "edited"
    if no_findings is not None:
        c.no_findings = bool(no_findings)
    if status is not None:
        c.status = status
    c.edited_by, c.edited_at = by, _now()
    db.flush()
    return c


ACCEPTED = ("accepted", "edited")


def completion_blockers(db: Session, run: AnalysisRun) -> List[str]:
    """What still stops the analysis being marked complete."""
    out = []
    if run.status != "done":
        return ["The analysis hasn't finished."]
    fs = findings(db, run)
    cs = {str(c.evaluation_subject_id) if c.evaluation_subject_id else None: c for c in conclusions(db, run)}
    for sid in run.results["order"]:
        name = run.results["subjects"][sid]["name"]
        has = any(str(f.evaluation_subject_id) == sid and f.status in ACCEPTED for f in fs)
        note = cs.get(sid)
        if not has and not (note and note.no_findings and note.status in ACCEPTED):
            out.append(f"{name}: accept at least one finding, or record that there's nothing to report.")
    overall = cs.get(None)
    if overall is None or overall.status not in ACCEPTED or not overall.text:
        out.append("Write and accept the overall conclusion.")
    return out


def mark_complete(db: Session, run: AnalysisRun, by: str) -> AnalysisRun:
    if run.completed_at:
        raise AnalysisError("Already marked complete.")
    blockers = completion_blockers(db, run)
    if blockers:
        raise AnalysisError("Not ready: " + " ".join(blockers))
    run.completed_by, run.completed_at = by, _now()
    db.flush()
    return run


# ----------------------------
# Comparing runs
# ----------------------------

def compare(db: Session, old: AnalysisRun, new: AnalysisRun) -> Dict[str, Any]:
    """What changed between two runs of the same evaluation, in plain terms."""
    changes = []
    a, b = old.results.get("subjects", {}), new.results.get("subjects", {})
    for sid in b:
        if sid not in a:
            changes.append({"subject": b[sid]["name"], "what": "New in this run", "before": None, "after": None})
    for sid in a:
        if sid not in b:
            changes.append({"subject": a[sid]["name"], "what": "No longer in this run", "before": None, "after": None})
    for sid in b:
        if sid not in a:
            continue
        for code, t in b[sid]["themes"].items():
            o = a[sid]["themes"].get(code)
            before = (o or {}).get("mean")
            after = t.get("mean")
            if o is None or before != after or o.get("raters") != t.get("raters") or bool(o.get("suppressed")) != bool(t.get("suppressed")):
                changes.append({"subject": b[sid]["name"], "what": t["label"],
                                "before": None if o is None else {"mean": before, "raters": o.get("raters"),
                                                                 "suppressed": bool(o.get("suppressed"))},
                                "after": {"mean": after, "raters": t.get("raters"), "suppressed": bool(t.get("suppressed"))}})
    old_p = {p["participant_id"] for p in old.inputs.get("participants", [])}
    new_p = {p["participant_id"] for p in new.inputs.get("participants", [])}
    count = lambda run, k: sum(1 for f in findings(db, run) if f.origin == "computed" and f.kind == k)  # noqa: E731
    kinds = ("strength", "concern", "observation", "compliance_gap", "self_perception_gap")
    return {
        "old_run": run_dict(old), "new_run": run_dict(new),
        "respondents": {"before": len(old_p), "after": len(new_p), "added": len(new_p - old_p),
                        "removed": len(old_p - new_p)},
        "evidence_rows": {"before": old.inputs.get("evidence_rows"), "after": new.inputs.get("evidence_rows")},
        "computed_findings": {k: {"before": count(old, k), "after": count(new, k)} for k in kinds},
        "changes": changes,
    }

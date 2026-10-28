"""
app.services.question_assembly
------------------------------
Assemble one draft question set per ready participant from the approved
question bank (Select), optionally with AI wording suggestions (Tailor).

Per participant, assembly:
- skips anyone who isn't READY (section 5 readiness), with the reasons;
- never changes an approved or locked set;
- runs selection (approved items; drafts only with ASSEMBLY_ALLOW_DRAFTS),
  respecting the evaluation's scope and peer_mode;
- fills placeholders, leaves known_from "skip" items out (listed), and turns
  known_from "confirm" items into confirm questions showing the stored value;
- links "If so..." follow-ups to the question they follow;
- orders by section, then subject, then bank sort order;
- checks coverage (subjects they can speak about with fewer than the floor)
  and, across the evaluation, deep sets with fewer than 3 raters;
- estimates completion time, counting the core peer grid as one fast block.

Re-running replaces a draft set but keeps consultant-edited questions,
questions a consultant added or removed, and accepted AI new questions,
unless reset is requested.

Counts, coverage and the time estimate are recomputed from the set's current
questions (set_metrics / refresh_summary) after assembly and after every
consultant change, so they never go stale.

Assembled questions live in the questions table with template_code
"P:<participant id>", so legacy template queries never see them.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AssemblyRun,
    Evaluation,
    EvaluationSubject,
    Organisation,
    ParticipantQuestionSet,
    Participant,
    Question,
    QuestionBankItem,
    QuestionBankItemClause,
    QuestionSubjectType,
    Theme,
)
from app.domain.question_bank import GRID_ITEM_PREFIX, SCALES, estimate_seconds
from app.services import question_tailoring as ai
from app.services.board_members import READY, participant_readiness
from app.services.profile_review import snapshot_context
from app.services.question_selection import (
    ROLE_LABELS,
    ROLE_TO_SUBJECT_TYPE,
    build_selection_context,
    eligible_items,
    item_spec,
    select_for_respondent,
)

log = logging.getLogger(__name__)

SECTIONS = ("board", "committees", "colleagues", "yourself", "confirm", "additional")
DEEP_SETS = {"DEEP-CHAIR-": "Chair deep set", "DEEP-MD-": "MD/CEO deep set", "DEEP-ED-": "ED deep set"}
MIN_RATERS = 3
FOLLOW_UP = re.compile(r"Ask only if the answer to ([A-Z][A-Z0-9-]*-\d{2,3}) is yes", re.I)


class AssemblyError(ValueError):
    """The request can't be carried out (HTTP 400)."""


class SetConflict(ValueError):
    """The set or question isn't in a state that allows this (HTTP 409)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def coverage_floor() -> int:
    try:
        return max(0, int(os.getenv("ASSEMBLY_COVERAGE_FLOOR", "2")))
    except ValueError:
        return 2


def drafts_allowed() -> bool:
    return (os.getenv("ASSEMBLY_ALLOW_DRAFTS") or "").strip().lower() in {"1", "true", "yes", "on"}


def template_code_for(participant_id) -> str:
    return f"P:{participant_id}"


# ----------------------------
# Runs
# ----------------------------

def create_run(db: Session, ev: Evaluation, *, participant_ids: Optional[List[str]] = None, reset: bool = False,
               include_drafts: bool = False, requested_by: Optional[str] = None) -> AssemblyRun:
    if include_drafts and not drafts_allowed():
        raise AssemblyError("Draft bank items can only be assembled when ASSEMBLY_ALLOW_DRAFTS is set (development only).")
    if participant_ids:
        known = {str(p) for p in db.execute(select(Participant.id).where(Participant.evaluation_id == ev.id)).scalars()}
        unknown = [p for p in participant_ids if p not in known]
        if unknown:
            raise AssemblyError(f"Not participants of this evaluation: {', '.join(unknown)}.")
    run = AssemblyRun(evaluation_id=ev.id, status="queued", participant_ids=participant_ids or None, reset=reset,
                      include_drafts=include_drafts, ai_enabled=ai.ai_tailoring_enabled(), requested_by=requested_by,
                      results=[], rater_warnings=[])
    db.add(run)
    db.flush()
    return run


def session_factory():
    """Session for background runs. Tests replace this to use their transaction."""
    from app.db.session import SessionLocal

    return SessionLocal()


def execute_run(run_id, llm_call: Optional[ai.LLMCall] = None) -> None:
    """Background entry point: run assembly in its own session and record the outcome."""
    db = session_factory()
    try:
        run = db.get(AssemblyRun, run_id)
        if run is None:
            return
        try:
            run_assembly(db, run, llm_call=llm_call)
            db.commit()
        except Exception as e:  # recorded on the run for the consultant
            log.exception("Assembly run %s failed", run_id)
            db.rollback()
            run = db.get(AssemblyRun, run_id)
            run.status = "failed"
            run.error = str(e)[:2000]
            run.finished_at = _now()
            db.commit()
    finally:
        db.close()


def run_assembly(db: Session, run: AssemblyRun, llm_call: Optional[ai.LLMCall] = None) -> AssemblyRun:
    ev = db.get(Evaluation, run.evaluation_id)
    run.status = "running"
    run.started_at = _now()
    db.flush()

    snap = snapshot_context(db, ev.id)
    run.snapshot_id = snap.id
    base = build_selection_context(db, ev)
    items = [item_spec(i) for i in eligible_items(db.execute(select(QuestionBankItem)).scalars().all(),
                                                    include_drafts=run.include_drafts)]
    readiness = {r["participant_id"]: r for r in participant_readiness(db, ev)}
    selections = {p["participant_id"]: select_for_respondent(items, base, p) for p in base["people"]}
    run.rater_warnings = rater_warnings(selections, base)

    tailoring = None
    if run.ai_enabled and ai.ai_tailoring_enabled():
        tailoring = TailoringContext(db, ev, base, snap, llm_call)

    wanted = set(run.participant_ids or [])
    results = []
    for person in base["people"]:
        pid = person["participant_id"]
        if wanted and pid not in wanted:
            continue
        results.append(assemble_participant(db, run, ev, base, person, selections[pid], readiness.get(pid), tailoring))
    run.results = results
    run.status = "done"
    run.finished_at = _now()
    db.flush()
    return run


# ----------------------------
# Subjects
# ----------------------------

def _ensure_subject(db: Session, ev: Evaluation, subject: Dict[str, Any], cache: Dict[str, EvaluationSubject],
                    secretary_pid: Optional[str]) -> EvaluationSubject:
    key = subject["key"]
    if key in cache:
        return cache[key]
    kind = subject["kind"]
    participant_id = None
    committee_name = None
    if kind == "person":
        participant_id = subject["participant_id"]
    elif kind == "committee":
        committee_name = subject["label"]
    elif kind == "function":
        participant_id = secretary_pid  # the secretariat is the company secretary's subject (single cardinality)
    stmt = select(EvaluationSubject).where(EvaluationSubject.evaluation_id == ev.id,
                                           EvaluationSubject.subject_type_code == subject["type"])
    stmt = stmt.where(EvaluationSubject.participant_id == participant_id) if participant_id else \
        stmt.where(EvaluationSubject.participant_id.is_(None))
    stmt = stmt.where(EvaluationSubject.committee_name == committee_name) if committee_name else \
        stmt.where(EvaluationSubject.committee_name.is_(None))
    row = db.execute(stmt).scalars().first()
    if row is None:
        row = EvaluationSubject(evaluation_id=ev.id, subject_type_code=subject["type"], participant_id=participant_id,
                                committee_name=committee_name, label=subject["label"][:255])
        db.add(row)
        db.flush()
    cache[key] = row
    return row


# ----------------------------
# Checks
# ----------------------------

def rater_warnings(selections: Dict[str, Dict[str, Any]], base: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deep sets with fewer than MIN_RATERS raters for a subject, across the whole evaluation."""
    labels = {p["participant_id"]: p["label"] for p in base["people"]}
    raters: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for pid, sel in selections.items():
        for e in sel["included"]:
            prefix = next((p for p in DEEP_SETS if e["code"].startswith(p)), None)
            if prefix is None:
                continue
            k = (prefix, e["subject"]["key"])
            slot = raters.setdefault(k, {"set": DEEP_SETS[prefix], "subject": e["subject"]["label"],
                                         "subject_key": e["subject"]["key"], "raters": set()})
            slot["raters"].add(pid)
    out = []
    for slot in raters.values():
        if len(slot["raters"]) < MIN_RATERS:
            out.append({
                "set": slot["set"], "subject": slot["subject"], "subject_key": slot["subject_key"],
                "rater_count": len(slot["raters"]), "raters": sorted(labels[p] for p in slot["raters"]),
                "message": (f"{slot['set']} about {slot['subject']} has {len(slot['raters'])} rater"
                            f"{'' if len(slot['raters']) == 1 else 's'}; results with fewer than {MIN_RATERS} "
                            "can't be reported individually."),
            })
    return sorted(out, key=lambda w: (w["set"], w["subject"]))


# ----------------------------
# One participant
# ----------------------------

def _section(entry: Dict[str, Any], pid: str) -> str:
    if entry.get("confirm"):
        return "confirm"
    s = entry["subject"]
    if s["kind"] in ("board", "function"):
        return "board"
    if s["kind"] == "committee":
        return "committees"
    return "yourself" if s.get("participant_id") == pid else "colleagues"


def _subject_order(base: Dict[str, Any]) -> Dict[str, int]:
    order: Dict[str, int] = {}
    for i, c in enumerate(sorted(base["committees"], key=lambda c: c["label"].lower())):
        order[f"committee:{c['committee_id']}"] = 100 + i
    for i, p in enumerate(base["people"]):
        order[f"person:{p['participant_id']}"] = 1000 + i
    return order


def renumber(questions: List[Question]) -> None:
    """Sort order by section, keeping the order within each section; steps of 10."""
    questions.sort(key=lambda q: (SECTIONS.index(q.section) if q.section in SECTIONS else len(SECTIONS),
                                  q.sort_order or 0))
    for n, q in enumerate(questions, start=1):
        q.sort_order = n * 10


def assemble_participant(db: Session, run: AssemblyRun, ev: Evaluation, base: Dict[str, Any], person: Dict[str, Any],
                         sel: Dict[str, Any], readiness: Optional[Dict[str, Any]],
                         tailoring: Optional["TailoringContext"]) -> Dict[str, Any]:
    pid = person["participant_id"]
    result = {"participant_id": pid, "label": person["label"],
              "role_label": ROLE_LABELS.get(person.get("role") or "", "Role not confirmed")}
    if readiness is None or readiness["status"] != READY:
        reasons = (readiness or {}).get("blocking_reasons") or ["Not ready."]
        return {**result, "outcome": "skipped", "reasons": reasons}
    pset = db.execute(select(ParticipantQuestionSet).where(ParticipantQuestionSet.participant_id == pid)).scalars().first()
    if pset is not None and pset.status != "draft":
        return {**result, "outcome": "skipped", "reasons": [f"The set is {pset.status}; assembly never changes it."]}
    if pset is None:
        pset = ParticipantQuestionSet(evaluation_id=ev.id, participant_id=pid, status="draft", summary={})
        db.add(pset)

    themes = {t.code: t.name for t in db.execute(select(Theme)).scalars().all()}
    secretary = next((p["participant_id"] for p in base["people"] if p.get("role") == "company_secretary"), None)
    subjects: Dict[str, EvaluationSubject] = {}
    order = _subject_order(base)
    codes_by_bank_id = {str(i.id): i.code for i in db.execute(select(QuestionBankItem)).scalars().all()}

    # Existing draft questions: unless resetting, keep consultant edits and removals (matched to the bank item
    # and subject), questions a consultant added, and accepted new questions
    existing = db.execute(select(Question).where(Question.participant_id == pid)).scalars().all()
    kept: Dict[Tuple[str, Optional[str]], Question] = {}
    kept_new: List[Question] = []
    for q in existing:
        key = (codes_by_bank_id.get(str(q.bank_item_id), ""), str(q.evaluation_subject_id))
        if not run.reset and q.bank_item_id and (q.text_source == "consultant_edited" or q.status == "removed"
                                                   or q.added_by):
            kept[key] = q
        elif not run.reset and (q.text_source == "consultant_written"
                                or (q.text_source == "ai_new" and q.suggestion_status == "accepted")):
            kept_new.append(q)
        else:
            db.delete(q)
    db.flush()

    questions: List[Tuple[Question, Dict[str, Any]]] = []
    for e in sel["included"]:
        subject = _ensure_subject(db, ev, e["subject"], subjects, secretary)
        section = _section(e, pid)
        key = (e["code"], str(subject.id))
        q = kept.pop(key, None)
        if q is None:
            q = Question(
                template_code=template_code_for(pid), version=1,
                dimension=themes.get(e["theme_code"], e["theme_code"]), text=e["text"], answer_type=e["answer_type"],
                weight=max(0, int(round(e.get("weight") or 1))), active=1, theme_code=e["theme_code"],
                evidence_source_code=e["evidence_source_code"], evaluation_id=ev.id, participant_id=pid,
                bank_item_id=uuid.UUID(e["bank_item_id"]), bank_item_version=e["version"], evaluation_subject_id=subject.id,
                status="draft", text_source="bank", options=e.get("options"), scale=e.get("scale"),
            )
            q.subject_type_links = [QuestionSubjectType(subject_type_code=e["subject"]["type"])]
            db.add(q)
        q.bank_text = e["text"]
        q.selection_reason = e.get("why")
        q.section = section
        q.confirm_value = ({k: e["confirm"][k] for k in ("known_from", "known_from_label", "value", "value_text")}
                           if e.get("confirm") else None)
        questions.append((q, e))
    for q in list(kept.values()):  # edited or removed questions whose item no longer applies
        if q.added_by:  # added by hand: stays even though selection doesn't pick it
            kept_new.append(q)
        else:
            db.delete(q)
    db.flush()

    # Order: section, subject, bank sort order
    def sort_key(pair):
        q, e = pair
        return (SECTIONS.index(q.section), order.get(e["subject"]["key"], 0), e.get("sort_order") or 0, e["code"])

    questions.sort(key=sort_key)
    for n, (q, _) in enumerate(questions, start=1):
        q.sort_order = n * 10
    for n, q in enumerate(kept_new, start=len(questions) + 1):
        if q.text_source == "ai_new":
            q.section = "additional"
        q.sort_order = n * 10
    renumber([q for q, _ in questions] + kept_new)  # hand-added questions back into their sections

    # Follow-ups: link to the question they follow, about the same subject
    by_code_subject = {(e["code"], str(q.evaluation_subject_id)): q for q, e in questions}
    unlinked = []
    for q, e in questions:
        m = FOLLOW_UP.search(e.get("guidance") or "")
        q.depends_on_question_id, q.show_if = None, None
        if not m:
            continue
        parent = by_code_subject.get((m.group(1).upper(), str(q.evaluation_subject_id)))
        if parent is None:
            unlinked.append({"code": e["code"], "follows": m.group(1).upper()})
            continue
        q.depends_on_question_id, q.show_if = parent.id, {"answer": "yes"}
    db.flush()

    # Every subject they're eligible to speak about, for live coverage (even ones with no question yet)
    coverage_subjects = []
    for e in sel["included"] + sel["skipped"] + sel["blocked"]:
        if any(c["key"] == e["subject"]["key"] for c in coverage_subjects):
            continue
        row = _ensure_subject(db, ev, e["subject"], subjects, secretary)
        coverage_subjects.append({"key": e["subject"]["key"], "subject_id": str(row.id), "label": e["subject"]["label"],
                                  "kind": e["subject"]["kind"], "type": e["subject"]["type"]})

    ai_summary = {"enabled": tailoring is not None}
    if tailoring is not None:
        ai_summary.update(tailoring.run_for(person, questions, kept_new))

    pset.status = "draft"
    pset.assembly_run_id = run.id
    pset.override_reason = None
    pset.summary = {
        "counts": {
            "kept_edits": sum(1 for q, _ in questions if q.text_source == "consultant_edited"),
            "skipped_known": len(sel["skipped"]),
            "blocked": len(sel["blocked"]),
        },
        "skipped_known": [{"code": e["code"], "text": e["text"], "subject": e["subject"]["label"],
                           "known_from": e["known_from_label"], "value": e["value_text"]} for e in sel["skipped"]],
        "blocked": [{"code": e["code"], "subject": e["subject"]["label"], "missing": e.get("missing") or []}
                    for e in sel["blocked"]],
        "follow_ups_without_parent": unlinked,
        "coverage_subjects": coverage_subjects,
        "ai": ai_summary,
    }
    m = refresh_summary(db, pset)
    return {**result, "outcome": "assembled", "questions": m["counts"]["questions"],
            "estimated_minutes": m["estimated_minutes"], "coverage_gaps": len(m["coverage_gaps"])}


# ----------------------------
# Live counts, coverage and time
# ----------------------------

def active_questions(questions: List[Question]) -> List[Question]:
    """What the participant would actually get: not removed, and AI new questions only once accepted."""
    return [q for q in questions if q.status != "removed"
            and not (q.text_source == "ai_new" and q.suggestion_status != "accepted")]


def set_metrics(db: Session, pset: ParticipantQuestionSet) -> Dict[str, Any]:
    """Counts, coverage per eligible subject, gaps and the time estimate from the set's current questions."""
    rows = list(db.execute(select(Question).where(Question.participant_id == pset.participant_id)).scalars().all())
    active = active_questions(rows)
    items = {i.id: i for i in db.execute(select(QuestionBankItem).where(
        QuestionBankItem.id.in_({q.bank_item_id for q in active if q.bank_item_id}))).scalars().all()}
    seconds = 0
    by_subject: Dict[str, int] = {}
    for q in active:
        item = items.get(q.bank_item_id)
        seconds += estimate_seconds(q.answer_type, confirm=q.section == "confirm", code=item.code if item else "",
                                    priority=(item.priority if item else None) or "standard")
        if q.evaluation_subject_id:
            by_subject[str(q.evaluation_subject_id)] = by_subject.get(str(q.evaluation_subject_id), 0) + 1
    floor = coverage_floor()
    summary = pset.summary or {}
    coverage, gaps = [], []
    for s in summary.get("coverage_subjects") or []:
        n = by_subject.get(s["subject_id"], 0)
        coverage.append({**s, "questions": n, "covered": n >= floor})
        if n < floor:
            gaps.append({"subject_key": s["key"], "subject_id": s["subject_id"], "subject": s["label"],
                         "kind": s["kind"], "questions": n, "floor": floor,
                         "message": f"Only {n} question{'' if n == 1 else 's'} about {s['label']} (floor {floor})."})
    if "coverage_subjects" not in summary:  # assembled before coverage was tracked live
        gaps = summary.get("coverage_gaps") or []
    return {
        "counts": {
            "questions": len(active),
            "by_section": {s: sum(1 for q in active if q.section == s) for s in SECTIONS},
            "confirm": sum(1 for q in active if q.section == "confirm"),
            "follow_ups": sum(1 for q in active if q.depends_on_question_id),
            "removed": sum(1 for q in rows if q.status == "removed"),
            "added": sum(1 for q in active if q.added_by),
            "pending_new": sum(1 for q in rows if q.text_source == "ai_new" and q.suggestion_status == "pending"),
            "open_wording": sum(1 for q in active if q.ai_text and q.text_source == "bank" and not q.suggestion_status),
        },
        "coverage": coverage,
        "coverage_gaps": gaps,
        "estimated_minutes": round(seconds / 60),
    }


def refresh_summary(db: Session, pset: ParticipantQuestionSet) -> Dict[str, Any]:
    """Recompute and store the set's counts, coverage gaps and time estimate; returns the metrics."""
    db.flush()
    m = set_metrics(db, pset)
    summary = dict(pset.summary or {})
    summary["counts"] = {**(summary.get("counts") or {}), **m["counts"]}
    summary["coverage_gaps"] = m["coverage_gaps"]
    pset.summary = summary
    pset.estimated_minutes = m["estimated_minutes"]
    db.flush()
    return m


def live_rater_warnings(db: Session, evaluation_id: str) -> List[Dict[str, Any]]:
    """Deep sets with fewer than MIN_RATERS raters for a subject, from the current sets across the evaluation."""
    rows = db.execute(
        select(Question, QuestionBankItem.code, EvaluationSubject.label, Participant.full_name, Participant.email)
        .join(QuestionBankItem, QuestionBankItem.id == Question.bank_item_id)
        .join(EvaluationSubject, EvaluationSubject.id == Question.evaluation_subject_id)
        .join(Participant, Participant.id == Question.participant_id)
        .where(Question.evaluation_id == evaluation_id, Question.status != "removed")
    ).all()
    raters: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for q, code, subject_label, name, email in rows:
        prefix = next((p for p in DEEP_SETS if code.startswith(p)), None)
        if prefix is None:
            continue
        slot = raters.setdefault((prefix, str(q.evaluation_subject_id)), {
            "set": DEEP_SETS[prefix], "subject": subject_label, "subject_id": str(q.evaluation_subject_id),
            "raters": {}})
        slot["raters"][str(q.participant_id)] = name or email
    out = []
    for slot in raters.values():
        n = len(slot["raters"])
        if n < MIN_RATERS:
            out.append({
                "set": slot["set"], "subject": slot["subject"], "subject_id": slot["subject_id"],
                "subject_key": slot["subject_id"], "rater_count": n, "raters": sorted(slot["raters"].values()),
                "participant_ids": sorted(slot["raters"]),
                "message": (f"{slot['set']} about {slot['subject']} has {n} rater{'' if n == 1 else 's'}; results with "
                            f"fewer than {MIN_RATERS} can't be reported individually."),
            })
    return sorted(out, key=lambda w: (w["set"], w["subject"]))


# ----------------------------
# AI tailoring for a run
# ----------------------------

class TailoringContext:
    """What the model may see for this evaluation, built once per run from the snapshot."""

    def __init__(self, db: Session, ev: Evaluation, base: Dict[str, Any], snap, llm_call):
        self.db = db
        self.llm_call = llm_call
        self._ev_id = ev.id
        org = db.get(Organisation, ev.organisation_id) if ev.organisation_id else None
        self.facts = {f["key"]: f["value"] for f in snap.facts}
        self.committees = [c["name"] for c in snap.committees]
        self.generation_only = snap.generation_only or {}
        period = None
        if ev.review_period_start or ev.review_period_end:
            period = f"{ev.review_period_start or '?'} to {ev.review_period_end or '?'}"
        self.context = {
            "company": {"name": org.name if org else ev.tenant_name, "sector": base["org"]["sector"],
                        "facts": self.facts},
            "committees": self.committees,
            "evaluation": {"name": ev.name, "review_period": period, "review_year": base["evaluation"]["review_year"],
                           "brief": ev.brief},
        }
        self.people = [p["label"].split(" · ", 1)[-1] for p in base["people"]] + \
                      [p["label"] for p in base["people"]]
        self.clauses: Dict[str, List[str]] = {}

    def _clauses(self, bank_item_id) -> List[str]:
        key = str(bank_item_id)
        if key not in self.clauses:
            links = self.db.execute(select(QuestionBankItemClause).where(
                QuestionBankItemClause.item_id == bank_item_id)).scalars().all()
            self.clauses[key] = [f"{x.clause.code} {x.clause.reference}: {x.clause.text[:400]}" for x in links]
        return self.clauses[key]

    def _tone(self, pid: str) -> Optional[str]:
        notes = [f["value"] for f in self.generation_only.get(pid, []) if f.get("key") == "personality_notes"]
        return notes[0] if notes else None

    def run_for(self, person: Dict[str, Any], questions: List[Tuple[Question, Dict[str, Any]]],
                kept_new: List[Question]) -> Dict[str, Any]:
        role = ROLE_LABELS.get(person.get("role") or "", "Director")
        context = {**self.context, "respondent": {"role": role, "tone_notes": self._tone(person["participant_id"])}}
        sent = []
        for q, e in questions:
            # Edited wording is the consultant's; core peer items share one grid header, so per-colleague
            # wording would break the grid
            if q.text_source == "consultant_edited" or e["code"].startswith(GRID_ITEM_PREFIX):
                continue
            subject = e["subject"]
            subject_name = subject["label"].split(" · ", 1)[-1] if subject["kind"] == "person" else None
            labels = (q.scale or {}).get("labels") or {}
            sent.append({
                "question_id": str(q.id), "bank_text": q.bank_text, "answer_type": q.answer_type,
                "options": q.options, "scale_labels": [labels[k] for k in sorted(labels, key=int)] or None,
                "subject": {"label": subject_name or subject["label"], "type": subject["type"]},
                "subject_name": subject_name, "committee": subject["label"] if subject["kind"] == "committee" else None,
                "clauses": self._clauses(q.bank_item_id), "guidance": e.get("guidance"),
            })
        vocab = ai.vocabulary(context, sent)
        checked = ai.tailor(sent, context, vocab, self.people, self.llm_call)
        by_id = {str(q.id): q for q, _ in questions}
        for q, _ in questions:
            if q.text_source != "consultant_edited":
                q.ai_text, q.ai_reason, q.suggestion_status = None, None, None
        for s in checked.accepted:
            q = by_id[s["question_id"]]
            q.ai_text, q.ai_reason = s["text"], s["reason"]

        # New questions: only where confirmed facts show something the selection doesn't cover
        allowed = ["BOARD"] + ([ROLE_TO_SUBJECT_TYPE[person["role"]]] if person.get("role") in ROLE_TO_SUBJECT_TYPE else [])
        selected_texts = [q.bank_text for q, _ in questions] + [q.text for q in kept_new]
        # Personality notes shape the tone of tailored wording only, so they're left out here
        plain = {**self.context, "respondent": {"role": role, "subject_type": allowed[-1]}}
        new = ai.suggest_new(plain, selected_texts, facts=self.facts, allowed_subject_types=allowed,
                             vocab=ai.vocabulary(plain), people=self.people, llm_call=self.llm_call)
        room = max(0, ai.MAX_NEW_QUESTIONS - len(kept_new))
        created = 0
        start = (len(questions) + len(kept_new) + 1) * 10
        for n, nq in enumerate(new.accepted[:room]):
            subject = self._subject_for(person, nq["subject_type"])
            q = Question(
                template_code=template_code_for(person["participant_id"]), version=1,
                dimension=self.db.get(Theme, nq["theme_code"]).name, text=nq["text"], answer_type=nq["answer_type"],
                weight=1, active=1, theme_code=nq["theme_code"], evidence_source_code=nq["evidence_source_code"],
                evaluation_id=self._ev_id, participant_id=person["participant_id"],
                evaluation_subject_id=subject.id if subject else None, section="additional",
                sort_order=start + n * 10, status="draft", text_source="ai_new", suggestion_status="pending",
                ai_text=nq["text"], ai_reason=nq["reason"], ai_fact_key=nq["fact_key"],
                options=nq.get("options") if nq["answer_type"] in ("single_select", "multi_select") else None,
                scale=SCALES["quality_5"] if nq["answer_type"] == "rating" else None,
            )
            q.subject_type_links = [QuestionSubjectType(subject_type_code=nq["subject_type"])]
            self.db.add(q)
            created += 1
        self.db.flush()
        return {
            "tailored": len(checked.accepted),
            "dropped": checked.dropped,
            "new_suggested": created,
            "new_dropped": new.dropped + [{**x, "dropped_because": "over the limit of 3 new questions"}
                                          for x in new.accepted[room:]],
        }

    def _subject_for(self, person: Dict[str, Any], subject_type: str) -> Optional[EvaluationSubject]:
        cache: Dict[str, EvaluationSubject] = {}
        if subject_type == "BOARD":
            subject = {"key": "board:BOARD", "kind": "board", "type": "BOARD", "label": "The board"}
        else:
            subject = {"key": f"person:{person['participant_id']}", "kind": "person", "type": subject_type,
                       "participant_id": person["participant_id"], "label": person["label"]}
        ev = self.db.get(Evaluation, self._ev_id)
        return _ensure_subject(self.db, ev, subject, cache, None)

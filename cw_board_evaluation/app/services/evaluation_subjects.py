"""
app.services.evaluation_subjects
--------------------------------
Build the concrete subjects of an evaluation (EvaluationSubject rows) from data
the evaluation already has. Idempotent: running it again creates nothing new.

Sources:
- BOARD: always one per evaluation.
- COMMITTEE: one per committee in the config of the evaluation's enabled
  committee tracks (EvaluationTrack.config["committees"]). That config is the
  source of truth: assignment generation reads committees from it and copies
  them onto AssessmentAssignment.committee_name. Committee names found only on
  assignments (e.g. a committee later removed from the config) are reported as
  skipped, not created.
- People: one subject per participant whose Participant.role maps to a subject
  type (see app.domain.taxonomy.ROLE_TO_SUBJECT_TYPE). For "single" types
  (CHAIR, MD_CEO, COMPANY_SECRETARY) more than one matching participant is
  ambiguous, so none of them is created. Unknown or empty roles are skipped.
  Nothing is guessed; every skip is returned with a reason.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AssessmentAssignment,
    AssessmentTrackTemplate,
    Evaluation,
    EvaluationSubject,
    EvaluationTrack,
    Participant,
    SubjectType,
)
from app.domain.taxonomy import (
    CARDINALITY_PER_PERSON,
    CARDINALITY_SINGLE,
    subject_type_for_role,
)
from app.services.committee_track_config import is_committee_track_template, normalize_committee_config


class EvaluationNotFound(LookupError):
    pass


def subject_to_dict(s: EvaluationSubject) -> Dict[str, Any]:
    return {
        "subject_id": str(s.id),
        "evaluation_id": s.evaluation_id,
        "subject_type_code": s.subject_type_code,
        "participant_id": str(s.participant_id) if s.participant_id else None,
        "committee_name": s.committee_name,
        "label": s.label,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def list_evaluation_subjects(db: Session, evaluation_id: str) -> List[EvaluationSubject]:
    order = {}  # subject type sort order, then label
    for code, sort_order in db.execute(select(SubjectType.code, SubjectType.sort_order)).all():
        order[code] = sort_order
    rows = db.execute(
        select(EvaluationSubject).where(EvaluationSubject.evaluation_id == evaluation_id)
    ).scalars().all()
    return sorted(rows, key=lambda s: (order.get(s.subject_type_code, 9999), s.label.lower()))


def _committees_from_config(db: Session, evaluation_id: str) -> List[str]:
    rows = db.execute(
        select(EvaluationTrack, AssessmentTrackTemplate)
        .join(AssessmentTrackTemplate, EvaluationTrack.track_template_id == AssessmentTrackTemplate.id)
        .where(EvaluationTrack.evaluation_id == evaluation_id)
        .where(EvaluationTrack.enabled == 1)
    ).all()
    names: List[str] = []
    seen = set()
    for et, tpl in rows:
        if not is_committee_track_template(tpl):
            continue
        for name in normalize_committee_config(et.config).get("committees") or []:
            if name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
    return names


def _committees_on_assignments(db: Session, evaluation_id: str) -> List[str]:
    rows = db.execute(
        select(AssessmentAssignment.committee_name)
        .where(AssessmentAssignment.evaluation_id == evaluation_id)
        .where(AssessmentAssignment.committee_name.is_not(None))
        .distinct()
    ).scalars().all()
    return sorted({(r or "").strip() for r in rows if (r or "").strip()}, key=str.lower)


def _participant_label(type_name: str, p: Participant) -> str:
    who = (p.full_name or "").strip() or p.email
    return f"{type_name}: {who}"[:255]


def sync_evaluation_subjects(db: Session, evaluation_id: str) -> Dict[str, Any]:
    """
    Create any missing subjects for the evaluation. Flushes but does not commit.

    Returns {"evaluation_id", "created": [...], "existing": [...], "skipped": [...]}
    where created/existing are subject dicts and skipped explains each item
    that was not turned into a subject.
    """
    if not db.get(Evaluation, evaluation_id):
        raise EvaluationNotFound(evaluation_id)

    types: Dict[str, SubjectType] = {t.code: t for t in db.execute(select(SubjectType)).scalars().all()}

    existing_rows = db.execute(
        select(EvaluationSubject).where(EvaluationSubject.evaluation_id == evaluation_id)
    ).scalars().all()

    def key_of(type_code: str, participant_id=None, committee_name: Optional[str] = None) -> Tuple:
        return (type_code, str(participant_id) if participant_id else None, (committee_name or "").lower() or None)

    by_key: Dict[Tuple, EvaluationSubject] = {
        key_of(s.subject_type_code, s.participant_id, s.committee_name): s for s in existing_rows
    }
    single_taken: Dict[str, EvaluationSubject] = {}
    for s in existing_rows:
        t = types.get(s.subject_type_code)
        if t and t.cardinality == CARDINALITY_SINGLE:
            single_taken.setdefault(s.subject_type_code, s)

    created: List[EvaluationSubject] = []
    existing: List[EvaluationSubject] = []
    skipped: List[Dict[str, Any]] = []

    def ensure(type_code: str, label: str, participant_id=None, committee_name: Optional[str] = None) -> None:
        if type_code not in types:
            skipped.append({"subject_type_code": type_code, "reason": "Subject type missing from subject_types table."})
            return
        k = key_of(type_code, participant_id, committee_name)
        if k in by_key:
            existing.append(by_key[k])
            return
        row = EvaluationSubject(
            evaluation_id=evaluation_id,
            subject_type_code=type_code,
            participant_id=participant_id,
            committee_name=committee_name,
            label=label[:255],
        )
        db.add(row)
        by_key[k] = row
        created.append(row)

    # 1. Board
    ensure("BOARD", types["BOARD"].name if "BOARD" in types else "Board as a whole")

    # 2. Committees (config is the source of truth)
    config_committees = _committees_from_config(db, evaluation_id)
    for name in config_committees:
        ensure("COMMITTEE", name, committee_name=name)
    config_keys = {n.lower() for n in config_committees}
    for name in _committees_on_assignments(db, evaluation_id):
        if name.lower() not in config_keys:
            skipped.append({
                "committee_name": name,
                "reason": "Committee appears on assignments but not in any enabled committee track config.",
            })

    # 3. People by role
    participants = db.execute(
        select(Participant).where(Participant.evaluation_id == evaluation_id).order_by(Participant.email)
    ).scalars().all()

    by_type: Dict[str, List[Participant]] = defaultdict(list)
    for p in participants:
        code = subject_type_for_role(p.role)
        if code is None:
            reason = "No role set." if not (p.role or "").strip() else f"Unknown role {p.role!r}."
            skipped.append({"participant_id": str(p.id), "email": p.email, "role": p.role, "reason": reason})
            continue
        by_type[code].append(p)

    for code, people in by_type.items():
        t = types.get(code)
        if t is None:
            for p in people:
                skipped.append({"participant_id": str(p.id), "email": p.email, "role": p.role,
                                "reason": f"Subject type {code} missing from subject_types table."})
            continue

        if t.cardinality == CARDINALITY_PER_PERSON:
            for p in people:
                ensure(code, _participant_label(t.name, p), participant_id=p.id)
            continue

        if t.cardinality == CARDINALITY_SINGLE:
            taken = single_taken.get(code)
            if len(people) > 1:
                for p in people:
                    skipped.append({"participant_id": str(p.id), "email": p.email, "role": p.role,
                                    "reason": f"Ambiguous: {len(people)} participants map to {code}, "
                                              "which allows one per evaluation."})
                continue
            p = people[0]
            if taken is not None and taken.participant_id != p.id:
                skipped.append({"participant_id": str(p.id), "email": p.email, "role": p.role,
                                "reason": f"Evaluation already has a {code} subject for another participant."})
                continue
            ensure(code, _participant_label(t.name, p), participant_id=p.id)
            continue

        # per_committee types can't come from a person's role
        for p in people:
            skipped.append({"participant_id": str(p.id), "email": p.email, "role": p.role,
                            "reason": f"Role maps to {code} ({t.cardinality}), which is not a per-person subject."})

    db.flush()
    return {
        "evaluation_id": evaluation_id,
        "created": [subject_to_dict(s) for s in created],
        "existing": [subject_to_dict(s) for s in existing],
        "skipped": skipped,
    }

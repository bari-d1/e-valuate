"""
Bootstrap demo evaluation: questions, participants, responses, tracks, assignments.

Usage:
  python scripts/seed_demo_environment.py
  python scripts/seed_demo_environment.py eval-002
  DEMO_EVALUATION_ID=eval-002 python scripts/seed_demo_environment.py
"""
from __future__ import annotations

import os
import random
import secrets
import sys
from datetime import datetime, timezone
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from sqlalchemy import select
from app.db.models import (
    AssessmentAssignment,
    AssessmentTrackTemplate,
    Evaluation,
    EvaluationTrack,
    Participant,
    Question,
    Response,
)
from app.db.session import SessionLocal
from app.questionnaires.presets import get_questions_for_preset

# Defaults match consultant UI (AppLegacy.jsx)
PRESETS = {
    "eval-demo-001": {
        "tenant_name": "Demo Client Plc",
        "sector": "insurance",
        "year": 2025,
        "regulators": ["NAICOM", "FRC"],
    },
    "eval-002": {
        "tenant_name": "EMOK Express",
        "sector": "insurance",
        "year": 2025,
        "regulators": ["NAICOM", "FRC"],
    },
}

TRACK_CODES = ["BOARD_AS_WHOLE", "DIRECTOR_SELF", "CHAIR_EVAL"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _unique_token(db, model, attr: str, max_tries: int = 12) -> str:
    for _ in range(max_tries):
        token = secrets.token_urlsafe(24)
        exists = db.execute(select(model).where(getattr(model, attr) == token)).scalar_one_or_none()
        if not exists:
            return token
    raise RuntimeError(f"Could not generate unique {model.__name__}.{attr}")


def seed_evaluation(db, eval_id: str, meta: dict) -> None:
    ev = db.get(Evaluation, eval_id)
    if not ev:
        ev = Evaluation(
            id=eval_id,
            tenant_name=meta["tenant_name"],
            sector=meta["sector"],
            year=int(meta["year"]),
            instrument_template_code="DEFAULT",
            instrument_version=1,
            regulators={"items": list(meta.get("regulators") or [])},
        )
        db.add(ev)
        db.commit()
        print(f"Created evaluation {eval_id} ({meta['tenant_name']})")
    else:
        ev.tenant_name = meta["tenant_name"]
        ev.sector = meta["sector"]
        ev.year = int(meta["year"])
        ev.regulators = {"items": list(meta.get("regulators") or [])}
        db.commit()
        print(f"Evaluation exists {eval_id} ({meta['tenant_name']})")

    tc, ver = "DEFAULT", 1
    existing_texts = set(
        (x or "").strip()
        for x in db.execute(
            select(Question.text).where(Question.template_code == tc, Question.version == ver)
        ).scalars().all()
    )
    q_created = 0
    for q in get_questions_for_preset("default"):
        if q["text"].strip() in existing_texts:
            continue
        db.add(
            Question(
                template_code=tc,
                version=ver,
                dimension=q["dimension"],
                text=q["text"],
                answer_type=q["answer_type"],
                weight=int(q.get("weight", 1)),
                active=1,
            )
        )
        q_created += 1
    db.commit()
    print(f"  Questions added to instrument: {q_created}")

    questions = db.execute(
        select(Question).where(
            Question.template_code == tc, Question.version == ver, Question.active == 1
        )
    ).scalars().all()
    rating_q = [q for q in questions if q.answer_type == "rating"]
    comment_q = [q for q in questions if q.answer_type == "comment"]
    rnd = random.Random(42)
    roles = ["Chair", "INED", "INED", "ED", "ED", "Company Secretary"]
    participants: List[Participant] = []
    for i in range(12):
        email = f"board_member_{i+1:02d}@demo-client.test"
        p = db.execute(
            select(Participant).where(
                Participant.evaluation_id == eval_id, Participant.email == email
            )
        ).scalar_one_or_none()
        if not p:
            p = Participant(
                evaluation_id=eval_id,
                email=email,
                full_name=f"Board Member {i+1:02d}",
                role=roles[i % len(roles)],
                status="invited",
                invited_at=utcnow(),
            )
            db.add(p)
            db.flush()
        participants.append(p)
    db.commit()

    db.commit()

    _seed_tracks_and_assignments(db, eval_id, participants, tc, ver)
    resp_created = _seed_assignment_responses(db, eval_id, participants, rating_q, comment_q, rnd, max_respondents=10)
    print(f"  Demo responses (assignment-linked): {resp_created} new rows")


def _seed_assignment_responses(
    db,
    eval_id: str,
    participants: List[Participant],
    rating_q: List[Question],
    comment_q: List[Question],
    rnd: random.Random,
    *,
    max_respondents: int = 10,
) -> int:
    """Seed demo answers on each participant's BOARD_AS_WHOLE assignment (portal-aligned)."""
    resp_created = 0
    for idx, p in enumerate(participants):
        if idx >= max_respondents:
            break

        assignment = db.execute(
            select(AssessmentAssignment)
            .where(AssessmentAssignment.evaluation_id == eval_id)
            .where(AssessmentAssignment.respondent_participant_id == p.id)
            .where(AssessmentAssignment.assignment_type == "BOARD_AS_WHOLE")
            .where(AssessmentAssignment.subject_participant_id.is_(None))
            .where(AssessmentAssignment.committee_name.is_(None))
        ).scalar_one_or_none()
        if not assignment:
            continue

        if p.status != "responded":
            p.status = "responded"
            p.responded_at = utcnow()
        if assignment.status != "responded":
            assignment.status = "responded"
            assignment.responded_at = utcnow()

        for q in rating_q:
            if db.execute(
                select(Response).where(
                    Response.assignment_id == assignment.id,
                    Response.question_id == q.id,
                )
            ).scalar_one_or_none():
                continue
            base = rnd.choices([2, 3, 4, 5], weights=[5, 25, 45, 25])[0]
            if q.dimension == "Risk Oversight":
                base = max(2, base - 1)
            db.add(
                Response(
                    evaluation_id=eval_id,
                    participant_id=p.id,
                    assignment_id=assignment.id,
                    question_id=q.id,
                    score=int(base),
                    comment=None,
                )
            )
            resp_created += 1

        if idx < 3 and comment_q:
            for q in comment_q:
                if db.execute(
                    select(Response).where(
                        Response.assignment_id == assignment.id,
                        Response.question_id == q.id,
                    )
                ).scalar_one_or_none():
                    continue
                db.add(
                    Response(
                        evaluation_id=eval_id,
                        participant_id=p.id,
                        assignment_id=assignment.id,
                        question_id=q.id,
                        score=None,
                        comment="Demo comment response.",
                    )
                )
                resp_created += 1

    db.commit()
    return resp_created


def _seed_tracks_and_assignments(
    db,
    eval_id: str,
    participants: List[Participant],
    template_code: str,
    version: int,
) -> None:
    for code in TRACK_CODES:
        tpl = db.execute(
            select(AssessmentTrackTemplate).where(AssessmentTrackTemplate.code == code)
        ).scalar_one_or_none()
        if not tpl:
            print(f"  Skip track {code}: template missing (run seed_reference_data.py)")
            continue

        et = db.execute(
            select(EvaluationTrack).where(
                EvaluationTrack.evaluation_id == eval_id,
                EvaluationTrack.track_template_id == tpl.id,
            )
        ).scalar_one_or_none()
        if not et:
            et = EvaluationTrack(
                evaluation_id=eval_id,
                track_template_id=tpl.id,
                enabled=1,
                config={},
            )
            db.add(et)
        else:
            et.enabled = 1
        db.commit()

    assignments_created = 0
    tpl_board = db.execute(
        select(AssessmentTrackTemplate).where(AssessmentTrackTemplate.code == "BOARD_AS_WHOLE")
    ).scalar_one_or_none()
    tpl_self = db.execute(
        select(AssessmentTrackTemplate).where(AssessmentTrackTemplate.code == "DIRECTOR_SELF")
    ).scalar_one_or_none()
    tpl_chair = db.execute(
        select(AssessmentTrackTemplate).where(AssessmentTrackTemplate.code == "CHAIR_EVAL")
    ).scalar_one_or_none()

    chair = next((p for p in participants if (p.role or "").strip().lower() == "chair"), None)
    ineds = [p for p in participants if (p.role or "").strip().upper() == "INED"]

    def _add_assignment(
        respondent: Participant,
        assignment_type: str,
        subject: Optional[Participant],
    ) -> None:
        nonlocal assignments_created
        subject_id = subject.id if subject else None
        existing = db.execute(
            select(AssessmentAssignment).where(
                AssessmentAssignment.evaluation_id == eval_id,
                AssessmentAssignment.respondent_participant_id == respondent.id,
                AssessmentAssignment.assignment_type == assignment_type,
                AssessmentAssignment.subject_participant_id == subject_id,
                AssessmentAssignment.committee_name.is_(None),
            )
        ).scalar_one_or_none()
        if existing:
            if not (existing.access_token or "").strip():
                existing.access_token = _unique_token(db, AssessmentAssignment, "access_token")
                existing.token_created_at = utcnow()
            return
        token = _unique_token(db, AssessmentAssignment, "access_token")
        db.add(
            AssessmentAssignment(
                evaluation_id=eval_id,
                respondent_participant_id=respondent.id,
                subject_participant_id=subject_id,
                assignment_type=assignment_type,
                instrument_template_code=template_code,
                instrument_version=version,
                access_token=token,
                token_created_at=utcnow(),
                status="invited",
                invited_at=utcnow(),
            )
        )
        db.flush()
        assignments_created += 1

    if tpl_board:
        for p in participants:
            _add_assignment(p, "BOARD_AS_WHOLE", None)

    if tpl_self:
        for p in participants:
            _add_assignment(p, "DIRECTOR_SELF", p)

    if tpl_chair and chair and ineds:
        for p in ineds:
            _add_assignment(p, "CHAIR_EVAL", chair)

    db.commit()
    total = db.execute(
        select(AssessmentAssignment).where(AssessmentAssignment.evaluation_id == eval_id)
    ).scalars().all()
    print(f"  Assignments for {eval_id}: {len(total)} total ({assignments_created} new)")


def main() -> None:
    eval_ids = sys.argv[1:] if len(sys.argv) > 1 else [os.getenv("DEMO_EVALUATION_ID", "eval-002").strip()]
    if not eval_ids or eval_ids == [""]:
        eval_ids = ["eval-002"]

    db = SessionLocal()
    try:
        for eval_id in eval_ids:
            meta = PRESETS.get(
                eval_id,
                {
                    "tenant_name": "Demo Client",
                    "sector": "insurance",
                    "year": 2025,
                    "regulators": ["NAICOM", "FRC"],
                },
            )
            seed_evaluation(db, eval_id, meta)
    finally:
        db.close()

    print("\nDone. Consultant UI default id is eval-002 (EMOK Express).")


if __name__ == "__main__":
    main()

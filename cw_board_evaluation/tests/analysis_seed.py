"""
Planted answers for the analysis on a VAL-001-style evaluation (placeholder names
and emails only). Every participant answers their whole form and submits. Default
answers are unremarkable (ratings of 3 or 4, factual items answered as good
practice expects); on top of that:

- P005 rates themselves 3 on "holds management to account"; peers average 4.6
- P002 rates themselves 5 on "open to challenge"; peers average 2.8, with two
  critical comments
- meeting management scores well (the board's effectiveness items and the chair's
  meeting items, all 5) and succession planning poorly (the chair's succession item,
  NCCG 1.5, and the risk and governance committee's succession items, NCCG 11.2.5.7)
- P007 answers "No" to "Is there an induction programme for new members?" (SEC-56,
  expected "Yes", NCCG 13 / NAICOM 3.0)
- P003's detailed (ED) set has only 2 raters, as assembled
- executives rate the board's dynamics 2, everyone else 5

Used by tests/test_analysis.py and scripts/seed_analysis_demo.py.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select

from app.db.models import BoardMember, EvaluationSubject, Participant, QuestionBankItem
from app.services import participant_portal as form

P005_PEERS = {"P001": 5, "P002": 5, "P003": 4, "P004": 5, "P006": 4}  # average 4.6
P002_PEERS = {"P001": 3, "P003": 3, "P004": 2, "P005": 3, "P006": 3}  # average 2.8
P002_COMMENTS = {
    "P004": "Dismisses challenge in board meetings and rarely changes course when directors push back.",
    "P005": "Should listen more when the board questions management proposals.",
}
EXECUTIVES = {"P002", "P003"}
SUCCESSION_LOW = {"CHAIR-PEER-17", "COM-ERMG-02", "COM-ERMG-03"}


def _code(db, participant_id) -> Optional[str]:
    p = db.get(Participant, participant_id)
    m = db.get(BoardMember, p.board_member_id) if p and p.board_member_id else None
    return m.display_code if m else None


def planted_value(q, item: Optional[QuestionBankItem], rater: str, subject: EvaluationSubject,
                  subject_code: Optional[str]) -> Any:
    code = item.code if item else ""
    if q.section == "confirm":
        return {"status": "correct"}
    at = q.answer_type
    if at == "rating":
        if code == "SELF-CORE-05" and rater == "P005":
            return 3
        if code == "PEER-CORE-05" and subject_code == "P005":
            return P005_PEERS[rater]
        if code == "SELF-CORE-06" and rater == "P002":
            return 5
        if code == "PEER-CORE-06" and subject_code == "P002":
            return P002_PEERS[rater]
        if code in SUCCESSION_LOW:
            return 2
        if subject.subject_type_code == "BOARD" and q.theme_code == "BOARD_DYNAMICS":
            return 2 if rater in EXECUTIVES else 5
        if subject.subject_type_code == "BOARD" and q.theme_code == "BOARD_EFFECTIVENESS":
            return 5
        if subject.subject_type_code == "CHAIR" and q.theme_code == "BOARD_EFFECTIVENESS":
            return 5
        return 3 if sum(map(ord, rater + code + str(subject.id))) % 3 == 0 else 4
    if at == "yesno":
        if code == "SEC-56":
            return "no"
        if item is not None and item.expected_answer:
            return item.expected_answer
        return "no" if q.evidence_source_code == "ROLE_SELF" else "yes"
    if at == "single_select":
        return (q.options or [None])[0]
    if at == "multi_select":
        return (q.options or [])[:2]
    if at == "comment":
        if code == "PEER-COMMENT-01" and subject_code == "P002" and rater in P002_COMMENTS:
            return P002_COMMENTS[rater]
        if q.evidence_source_code == "ORG_FACT":
            return "Placeholder factual answer."
        return None
    return None


def seed_planted(db, ev, parts: Dict[str, Participant], *, unsubmitted: tuple = (),
                 skip: tuple = ()) -> Dict[str, str]:
    """
    Approved sets must exist. Answers every form (except `skip`) and submits it (except `unsubmitted`,
    which stay in progress); returns the form tokens.
    """
    subjects = {s.id: s for s in db.execute(select(EvaluationSubject).where(
        EvaluationSubject.evaluation_id == ev.id)).scalars()}
    tokens = {}
    for code, p in parts.items():
        a = form.ensure_form_assignment(db, p, form.question_set(db, p.id))
        tokens[code] = a.access_token
        if code in skip:
            continue
        form.open_form(db, a.access_token)
        questions = form.form_questions(db, p.id)
        items = {i.id: i for i in db.execute(select(QuestionBankItem).where(
            QuestionBankItem.id.in_({q.bank_item_id for q in questions if q.bank_item_id}))).scalars()}
        answers = []
        for q in questions:
            s = subjects.get(q.evaluation_subject_id)
            if s is None:
                continue
            v = planted_value(q, items.get(q.bank_item_id), code, s, _code(db, s.participant_id) if s.participant_id else None)
            if v is not None:
                answers.append({"question_id": str(q.id), "value": v})
        form.save_answers(db, a.access_token, answers)
        if code not in unsubmitted:
            out = form.submit(db, a.access_token)
            assert out["submitted"], (code, out["missing"][:3])
    db.flush()
    return tokens

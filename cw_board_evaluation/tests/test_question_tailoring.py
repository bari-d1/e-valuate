"""
AI tailoring and new-question suggestions, with the model mocked: the
validator drops bad suggestions, personality notes only reach tailoring,
new questions are capped at 3 and stored as drafts, and with the setting off
nothing calls a model at all.

The validator tests are pure; the assembly tests need RUN_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select, update

from ai.prompts.question_tailoring import NEW_QUESTIONS_SYSTEM_PROMPT, TAILOR_SYSTEM_PROMPT
from app.db.models import BoardMemberFact, OrganisationFact, Question, QuestionBankItem
from app.services import question_assembly as qa
from app.services import question_sets as qs
from app.services import question_tailoring as ai
from app.services.question_bank import load_fixture
from app.services.question_selection import preview
from tests.val001 import build_val001

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"

# ----------------------------
# Validator (pure)
# ----------------------------

Q = {"question_id": "q1", "bank_text": "Board committees carry out their duties effectively and report promptly to the board",
     "answer_type": "rating", "subject_name": None}
VOCAB = ai.vocabulary(Q["bank_text"], "Audit and Compliance Committee", "review period 2025", {"name": "Test company specific"})
PEOPLE = ["Board Member 004", "Board Member 005"]


def _reply(**s):
    return json.dumps({"suggestions": [{"question_id": "q1", "reason": "Names the real committee", **s}]})


@pytest.mark.parametrize("text, extra, dropped_because", [
    ("The Audit and Compliance Committee carries out its duties effectively and reports promptly to the board", {}, None),
    ("Committees carry out their duties effectively", {"answer_type": "yesno"}, "changes the answer type"),
    ("Do board committees carry out their duties effectively?", {}, "yes/no question"),
    ("Board committees, led by Board Member 005, report promptly to the board", {}, "names someone other than the subject"),
    ("Since the Lagos merger, board committees report promptly to the board", {}, "not in the context (Lagos)"),
    ("Board committees report promptly to the board, as in 2019", {}, "not in the context (2019)"),
    ("Board committees, including Company-specific ones, report promptly to the board", {}, None),
    ("Board committees obviously carry out their duties and report promptly to the board", {}, "leading or loaded"),
    ("Board committees carry out their duties effectively and report promptly to the board " * 3, {}, "much longer"),
    ("The Audit and Compliance Committee and others report promptly to the board", {}, None),
])
def test_validator(text, extra, dropped_because) -> None:
    checked = ai.validate_suggestions(_reply(text=text, **extra), [Q], VOCAB, PEOPLE)
    if dropped_because is None:
        assert checked.accepted and not checked.dropped
    else:
        assert not checked.accepted
        assert dropped_because in checked.dropped[0]["dropped_because"], checked.dropped


def test_validator_allows_the_subjects_own_name() -> None:
    q = {**Q, "bank_text": "Comes to board meetings well prepared", "subject_name": "Board Member 004"}
    vocab = ai.vocabulary(q["bank_text"], "Board Member 004")
    ok = ai.validate_suggestions(_reply(text="Board Member 004 comes to board meetings well prepared"), [q], vocab, PEOPLE)
    assert ok.accepted
    others = [n for n in PEOPLE if n != q["subject_name"]]
    assert ai.check_suggestion(ai.Suggestion(question_id="q1", text="Comes better prepared than Board Member 005",
                                             reason="Comparison"), q, vocab, others)


def test_validator_keeps_committee_items_to_their_own_committee() -> None:
    committees = ["Audit and Compliance Committee", "Finance and Investment Committee"]
    vocab = ai.vocabulary(*committees, "The committee receives adequate materials before its meetings")
    about_audit = {"question_id": "q1", "bank_text": "The committee receives adequate materials before its meetings",
                   "answer_type": "rating", "subject_name": None, "committee": "Audit and Compliance Committee"}
    ok = ai.validate_suggestions(_reply(text="The Audit and Compliance Committee receives adequate materials before "
                                             "its meetings"), [about_audit], vocab, PEOPLE, committees)
    assert ok.accepted
    wrong = ai.validate_suggestions(_reply(text="The Finance and Investment Committee receives adequate materials before "
                                                "its meetings"), [about_audit], vocab, PEOPLE, committees)
    assert "names a committee the question isn't about" in wrong.dropped[0]["dropped_because"]
    board_item = {**about_audit, "committee": None, "bank_text": "The board receives adequate papers before its meetings"}
    narrowed = ai.validate_suggestions(_reply(text="The Finance and Investment Committee receives adequate papers before "
                                                   "its meetings"), [board_item], vocab, PEOPLE, committees)
    assert "narrows the question to a committee" in narrowed.dropped[0]["dropped_because"]


def test_invalid_reply_is_dropped_not_raised() -> None:
    checked = ai.validate_suggestions("not json", [Q], VOCAB, PEOPLE)
    assert not checked.accepted and "invalid reply" in checked.dropped[0]["dropped_because"]


# ----------------------------
# With assembly (integration)
# ----------------------------

class FakeModel:
    """Answers both prompts (tailoring: the first batch only); records what it was sent."""

    def __init__(self):
        self.calls = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if system == TAILOR_SYSTEM_PROMPT:
            if sum(1 for s, _ in self.calls if s == TAILOR_SYSTEM_PROMPT) > 1:
                return json.dumps({"suggestions": []})
            questions = json.loads(user.split("QUESTIONS:\n", 1)[1].split("\n\nCONSULTANT NOTE", 1)[0])
            ratings = [q for q in questions if q["answer_type"] == "rating"][:5]
            out = []
            for n, q in enumerate(ratings):
                bank = q["bank_text"].rstrip(".?")
                out.append([
                    {"text": f"{bank}, during the review period", "answer_type": "rating"},
                    {"text": f"{bank}?", "answer_type": "yesno"},
                    {"text": f"{bank}, compared with Board Member 005", "answer_type": "rating"},
                    {"text": f"{bank}, since the Lagos merger", "answer_type": "rating"},
                    {"text": f"Does the director do this: {bank.lower()}?", "answer_type": "rating"},
                ][n] | {"question_id": q["question_id"], "reason": "Tailored"})
            return json.dumps({"suggestions": out})
        assert system == NEW_QUESTIONS_SYSTEM_PROMPT
        base = {"subject_type": "BOARD", "theme_code": "STRATEGY", "evidence_source_code": "PERCEPTION",
                "answer_type": "rating", "reason": "Recent events mention a merger", "fact_key": "recent_events"}
        return json.dumps({"questions": [
            {**base, "text": "The board oversaw the integration after the merger effectively"},
            {**base, "text": "The board understood the risks of the merger before approving it"},
            {**base, "text": "The board monitors the merger's benefits against the plan"},
            {**base, "text": "The board has the information it needs on the merged business"},
            {**base, "text": "The board reviewed the shoe policy", "fact_key": "shoe_size"},
        ]})


@pytest.fixture
def val001(db_session, reference_seeded):
    load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    db_session.execute(update(QuestionBankItem).values(status="approved"))
    ev, parts, committees = build_val001(db_session)
    db_session.add(OrganisationFact(organisation_id=ev.organisation_id, key="recent_events", value=["Completed a merger in 2025"],
                                    source="client", status="confirmed", origin="manual"))
    db_session.add(BoardMemberFact(board_member_id=parts["P006"].board_member_id, key="personality_notes",
                                   value="Prefers short, direct questions", source="client", status="confirmed",
                                   origin="manual"))
    db_session.flush()
    return ev, parts, committees


def _assemble(db, ev, model, participant_ids=None):
    run = qa.create_run(db, ev, participant_ids=participant_ids)
    qa.run_assembly(db, run, llm_call=model)
    return run


@pytest.mark.integration
def test_ai_suggestions_are_checked_and_stored_as_suggestions_only(db_session, val001, monkeypatch) -> None:
    ev, parts, _ = val001
    monkeypatch.setenv("AI_TAILORING_ENABLED", "true")
    model = FakeModel()
    _assemble(db_session, ev, model, [str(parts["P004"].id)])
    rows = db_session.execute(select(Question).where(Question.participant_id == parts["P004"].id)).scalars().all()
    tailored = [q for q in rows if q.ai_text and q.text_source != "ai_new"]
    assert len(tailored) == 1
    assert tailored[0].ai_text.endswith(", during the review period") and tailored[0].ai_reason == "Tailored"
    assert all(q.text == q.bank_text and q.text_source == "bank" for q in rows if q.text_source != "ai_new")
    # Core peer grid items share one header, so they're never sent for tailoring
    sent = "".join(u for s, u in model.calls if s == TAILOR_SYSTEM_PROMPT)
    assert "Comes to board meetings well prepared" not in sent and "Your preparation for board meetings" in sent
    summary = qs.question_set(db_session, parts["P004"].id).summary["ai"]
    reasons = sorted(d["dropped_because"].split(" (")[0] for d in summary["dropped"])
    assert reasons == ["changes the answer type", "mentions something not in the context",
                       "names someone other than the subject", "turns a rating item into a yes/no question"]
    # New questions: 4 valid, capped at 3; the one citing an unknown fact is dropped
    new = [q for q in rows if q.text_source == "ai_new"]
    assert len(new) == 3
    assert all(q.status == "draft" and q.suggestion_status == "pending" and q.section == "additional" for q in new)
    assert all(q.ai_fact_key == "recent_events" and q.theme_code == "STRATEGY" and q.subject_type_codes == ["BOARD"]
               for q in new)
    assert sorted(d["dropped_because"].split(" (")[0].split(",")[0] for d in summary["new_dropped"]) == [
        "cites 'shoe_size'", "over the limit of 3 new questions"]
    # Approving never includes pending suggestions
    pset = qs.question_set(db_session, parts["P004"].id)
    qs.decide_new(db_session, new[0], True, "tester")
    qs.decide_new(db_session, new[1], False, "tester")
    qs.approve_set(db_session, pset, "tester")
    assert [q.status for q in new] == ["approved", "draft", "draft"]


@pytest.mark.integration
def test_personality_notes_only_reach_tailoring(db_session, val001, monkeypatch) -> None:
    ev, parts, _ = val001
    monkeypatch.setenv("AI_TAILORING_ENABLED", "true")
    model = FakeModel()
    _assemble(db_session, ev, model, [str(parts["P006"].id)])
    tailor_prompts = [u for s, u in model.calls if s == TAILOR_SYSTEM_PROMPT]
    new_prompts = [u for s, u in model.calls if s == NEW_QUESTIONS_SYSTEM_PROMPT]
    assert tailor_prompts and all("Prefers short, direct questions" in u for u in tailor_prompts)
    assert new_prompts and not any("Prefers short" in u for u in new_prompts)
    assert "Prefers short" not in json.dumps(preview(db_session, ev, include_drafts=False))
    assert "Prefers short" not in json.dumps(qs.set_dict(db_session, ev.id, parts["P006"]), default=str)


@pytest.mark.integration
def test_disabled_setting_means_no_ai_calls(db_session, val001, monkeypatch) -> None:
    ev, parts, _ = val001
    monkeypatch.delenv("AI_TAILORING_ENABLED", raising=False)

    def forbidden(*a, **k):
        raise AssertionError("a model was called with AI tailoring off")

    monkeypatch.setattr(ai, "default_llm_call", forbidden)
    run = _assemble(db_session, ev, forbidden)
    assert run.ai_enabled is False and [r["outcome"] for r in run.results] == ["assembled"] * 7
    rows = db_session.execute(select(Question).where(Question.evaluation_id == ev.id)).scalars().all()
    assert rows and all(q.ai_text is None and q.text == q.bank_text for q in rows)
    with pytest.raises(qa.SetConflict):
        qs.regenerate(db_session, rows[0], "shorter")


@pytest.mark.integration
def test_regenerate_one_question_with_a_note(db_session, val001, monkeypatch) -> None:
    ev, parts, _ = val001
    monkeypatch.setenv("AI_TAILORING_ENABLED", "true")
    model = FakeModel()
    _assemble(db_session, ev, model, [str(parts["P004"].id)])
    q = next(q for q in db_session.execute(select(Question).where(Question.participant_id == parts["P004"].id))
             .scalars() if q.answer_type == "rating" and q.text_source == "bank")
    again = FakeModel()
    out = qs.regenerate(db_session, q, note="Mention the review period", llm_call=again)
    assert out["accepted"] and q.ai_text.endswith(", during the review period")
    assert "CONSULTANT NOTE (apply to the question): Mention the review period" in again.calls[-1][1]

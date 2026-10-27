"""
app.services.question_tailoring
-------------------------------
AI suggestions for assembled questions: tailored wording for each question,
and at most 3 new questions per participant where the context shows a gap.

Guarded by AI_TAILORING_ENABLED (default false): the client hasn't yet
confirmed that client data may be sent to OpenAI. When it's off, nothing here
calls a model and assembly uses bank text.

The model only suggests. Every reply is validated in code, and a suggestion
is dropped (with the reason kept for review) when it:
- changes the answer type, or turns a rating/choice into a yes/no question,
- is much longer than the bank text,
- uses loaded wording the bank text doesn't,
- names anyone other than the question's subject, or a committee other than
  the one the question is about,
- mentions a name, word or number that isn't in the context passed in.
Bank text stays the default until a consultant picks a suggestion.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from pydantic import BaseModel, Field, ValidationError

from ai.prompts.question_tailoring import (
    NEW_QUESTIONS_SYSTEM_PROMPT,
    TAILOR_SYSTEM_PROMPT,
    build_new_questions_prompt,
    build_tailor_prompt,
)
from app.domain.question_bank import ANSWER_TYPES, SELECT_TYPES
from app.domain.question_rules import ORG_FACT_KEYS
from app.domain.taxonomy import EVIDENCE_SOURCE_CODES, THEME_CODES

LLMCall = Callable[[str, str], str]  # (system, user) -> raw text reply

MAX_NEW_QUESTIONS = 3
MAX_NEW_QUESTION_CHARS = 300
BATCH_SIZE = 40

# Words that make a question leading or loaded; allowed only if the bank text already uses them
LOADED_WORDS = (
    "obviously", "clearly", "surely", "of course", "undoubtedly", "don't you", "wouldn't you", "isn't it",
    "aren't they", "fail", "failed", "failure", "poor", "poorly", "excellent", "outstanding", "brilliant",
    "terrible", "weak", "strong", "great", "admirable", "disappointing",
)
YES_NO_OPENERS = ("do", "does", "did", "is", "are", "was", "were", "has", "have", "had", "can", "could", "will",
                  "would", "should", "shall")
# Capitalised words that need no source in the context
COMMON_CAPITALISED = {
    "board", "committee", "committees", "chair", "chairman", "chairperson", "md", "ceo", "md/ceo", "ned", "neds",
    "ined", "ineds", "ed", "eds", "executive", "executives", "director", "directors", "company", "management",
    "nccg", "naicom", "agm", "i", "the", "a", "an", "how", "what", "which", "when", "where", "why", "who", "to",
    "in", "on", "please", "rate", "describe", "list", "independent", "non-executive", "managing", "chief",
    "officer", "secretary", "technical", "general", "manager", "senior", "select", "all", "apply", "tick",
}


def ai_tailoring_enabled() -> bool:
    return (os.getenv("AI_TAILORING_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def default_llm_call(system: str, user: str) -> str:
    from app.services.org_extraction import default_llm_call as call

    return call(system, user)


# ----------------------------
# Reply shapes
# ----------------------------

class Suggestion(BaseModel):
    question_id: str
    text: str = Field(min_length=3, max_length=800)
    reason: str = Field(min_length=3, max_length=400)
    answer_type: Optional[str] = None


class TailorReply(BaseModel):
    suggestions: List[Suggestion] = []


class NewQuestion(BaseModel):
    text: str = Field(min_length=10, max_length=800)
    reason: str = Field(min_length=3, max_length=400)
    fact_key: str
    subject_type: str
    theme_code: str
    evidence_source_code: str
    answer_type: str
    options: Optional[List[str]] = None


class NewQuestionsReply(BaseModel):
    questions: List[NewQuestion] = []


def _json(raw: str) -> Any:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s.lower().startswith("json"):
            s = s[4:].strip()
    return json.loads(s)


# ----------------------------
# Checks (pure)
# ----------------------------

def _words(text: str) -> Set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'’/&.-]*", text or "")}


def vocabulary(*texts: Any) -> Set[str]:
    """Every word (lower case) in the texts or JSON-able values the model was given."""
    out: Set[str] = set()
    for t in texts:
        t = t if isinstance(t, str) else json.dumps(t, ensure_ascii=False, default=str)
        for w in _words(t):
            w = w.strip(".,;:'’")
            out.add(w)
            out.update(p for p in re.split(r"[-/]", w) if p)
    return out


def unknown_terms(text: str, vocab: Set[str]) -> List[str]:
    """Capitalised words (not opening a sentence) and numbers that aren't in the context."""
    found: List[str] = []
    for sentence in re.split(r"(?<=[.?!])\s+", text.strip()):
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’/&-]*", sentence)
        for i, tok in enumerate(tokens):
            low = tok.lower().strip("'’")
            is_number = bool(re.match(r"^\d", tok))
            is_proper = tok[0].isupper() and i > 0
            if not (is_number or is_proper):
                continue
            parts = [p for p in re.split(r"[-/]", low) if p]
            if all(p in COMMON_CAPITALISED or p in vocab or p.rstrip("s") in vocab for p in parts):
                continue
            if tok not in found:
                found.append(tok)
    return found


def names_in(text: str, names: List[str]) -> List[str]:
    low = (text or "").lower()
    return [n for n in names if n and n.lower() in low]


@dataclass
class Checked:
    accepted: List[Dict[str, Any]] = field(default_factory=list)
    dropped: List[Dict[str, Any]] = field(default_factory=list)


def check_suggestion(s: Suggestion, q: Dict[str, Any], vocab: Set[str], other_names: List[str],
                     committees: Optional[List[str]] = None) -> Optional[str]:
    """Why a tailoring suggestion must be dropped, or None if it may be offered."""
    bank, ai = q["bank_text"].strip(), s.text.strip()
    if s.answer_type and s.answer_type != q["answer_type"]:
        return f"changes the answer type ({q['answer_type']} to {s.answer_type})"
    if ai.lower() == bank.lower():
        return "same as the bank text"
    first = (re.findall(r"[A-Za-z]+", ai) or [""])[0].lower()
    bank_first = (re.findall(r"[A-Za-z]+", bank) or [""])[0].lower()
    if q["answer_type"] != "yesno" and first in YES_NO_OPENERS and bank_first not in YES_NO_OPENERS and ai.endswith("?"):
        return f"turns a {q['answer_type']} item into a yes/no question"
    if len(ai) > max(int(len(bank) * 1.5), len(bank) + 60):
        return f"much longer than the bank text ({len(ai)} vs {len(bank)} characters)"
    loaded = [w for w in LOADED_WORDS if re.search(rf"\b{re.escape(w)}\b", ai.lower())
              and not re.search(rf"\b{re.escape(w)}\b", bank.lower())]
    if loaded:
        return f"leading or loaded wording ({', '.join(loaded)})"
    named = names_in(ai, other_names)
    if named:
        return f"names someone other than the subject ({', '.join(named)})"
    own = (q.get("committee") or "").lower()
    wrong = [c for c in names_in(ai, committees or []) if c.lower() != own and c.lower() not in bank.lower()]
    if wrong:
        return (f"names a committee the question isn't about ({', '.join(wrong)})" if own
                else f"narrows the question to a committee ({', '.join(wrong)})")
    unknown = unknown_terms(ai, vocab)
    if unknown:
        return f"mentions something not in the context ({', '.join(unknown)})"
    return None


def validate_suggestions(raw: str, questions: List[Dict[str, Any]], vocab: Set[str],
                         people: List[str], committees: Optional[List[str]] = None) -> Checked:
    """
    Parse and check a tailoring reply. `questions` are the dicts sent to the
    model (question_id, bank_text, answer_type, subject_name, committee);
    `people` are every person's name in the evaluation and `committees` every
    committee's name.
    """
    out = Checked()
    try:
        reply = TailorReply.model_validate(_json(raw))
    except (ValueError, ValidationError) as e:
        out.dropped.append({"question_id": None, "text": (raw or "")[:200], "dropped_because": f"invalid reply: {e}"[:300]})
        return out
    by_id = {q["question_id"]: q for q in questions}
    seen: Set[str] = set()
    for s in reply.suggestions:
        q = by_id.get(s.question_id)
        why = None
        if q is None:
            why = "refers to a question that wasn't sent"
        elif s.question_id in seen:
            why = "second suggestion for the same question"
        else:
            others = [n for n in people if n.lower() != (q.get("subject_name") or "").lower()]
            why = check_suggestion(s, q, vocab, others, committees)
        seen.add(s.question_id)
        if why:
            out.dropped.append({"question_id": s.question_id, "text": s.text, "reason": s.reason, "dropped_because": why})
        else:
            out.accepted.append({"question_id": s.question_id, "text": s.text.strip(), "reason": s.reason.strip()})
    return out


def validate_new_questions(raw: str, *, facts: Dict[str, Any], allowed_subject_types: List[str], vocab: Set[str],
                           people: List[str], existing_texts: List[str]) -> Checked:
    out = Checked()
    try:
        reply = NewQuestionsReply.model_validate(_json(raw))
    except (ValueError, ValidationError) as e:
        out.dropped.append({"text": (raw or "")[:200], "dropped_because": f"invalid reply: {e}"[:300]})
        return out
    existing = {re.sub(r"\W+", " ", t.lower()).strip() for t in existing_texts}
    for nq in reply.questions:
        why = None
        if nq.fact_key not in ORG_FACT_KEYS or nq.fact_key.split(".")[0] not in facts:
            why = f"cites {nq.fact_key!r}, which isn't a confirmed fact in the context"
        elif nq.subject_type not in allowed_subject_types:
            why = f"subject type {nq.subject_type} isn't allowed (only {', '.join(allowed_subject_types)})"
        elif nq.theme_code not in THEME_CODES or nq.evidence_source_code not in EVIDENCE_SOURCE_CODES:
            why = "unknown theme or evidence source"
        elif nq.answer_type not in ANSWER_TYPES:
            why = f"unknown answer type {nq.answer_type!r}"
        elif nq.answer_type in SELECT_TYPES and len([o for o in nq.options or [] if o.strip()]) < 2:
            why = "a choice question needs at least two options"
        elif len(nq.text) > MAX_NEW_QUESTION_CHARS:
            why = f"too long ({len(nq.text)} characters)"
        elif re.sub(r"\W+", " ", nq.text.lower()).strip() in existing:
            why = "duplicates a question already in the set"
        else:
            loaded = [w for w in LOADED_WORDS if re.search(rf"\b{re.escape(w)}\b", nq.text.lower())]
            named = names_in(nq.text, people)
            unknown = unknown_terms(nq.text + " " + " ".join(nq.options or []), vocab)
            why = (f"leading or loaded wording ({', '.join(loaded)})" if loaded
                   else f"names a person ({', '.join(named)})" if named
                   else f"mentions something not in the context ({', '.join(unknown)})" if unknown else None)
        if why is None and len(out.accepted) >= MAX_NEW_QUESTIONS:
            why = f"over the limit of {MAX_NEW_QUESTIONS} new questions"
        entry = nq.model_dump()
        if why:
            out.dropped.append({**entry, "dropped_because": why})
        else:
            out.accepted.append(entry)
    return out


# ----------------------------
# Calls
# ----------------------------

def tailor(questions: List[Dict[str, Any]], context: Dict[str, Any], vocab: Set[str], people: List[str],
           llm_call: Optional[LLMCall] = None, note: str = "") -> Checked:
    committees = list(context.get("committees") or [])
    """Ask for wording suggestions in batches and validate every reply."""
    call = llm_call or default_llm_call
    result = Checked()
    for start in range(0, len(questions), BATCH_SIZE):
        batch = questions[start:start + BATCH_SIZE]
        sent = [{k: q[k] for k in ("question_id", "bank_text", "answer_type", "options", "scale_labels", "subject",
                                   "clauses", "guidance") if k in q} for q in batch]
        raw = call(TAILOR_SYSTEM_PROMPT, build_tailor_prompt(context, sent, note))
        checked = validate_suggestions(raw, batch, vocab, people, committees)
        result.accepted += checked.accepted
        result.dropped += checked.dropped
    return result


def suggest_new(context: Dict[str, Any], selected_texts: List[str], *, facts: Dict[str, Any],
                allowed_subject_types: List[str], vocab: Set[str], people: List[str],
                llm_call: Optional[LLMCall] = None) -> Checked:
    call = llm_call or default_llm_call
    tags = {"theme_codes": THEME_CODES, "evidence_source_codes": EVIDENCE_SOURCE_CODES,
            "answer_types": list(ANSWER_TYPES), "subject_types": allowed_subject_types}
    raw = call(NEW_QUESTIONS_SYSTEM_PROMPT, build_new_questions_prompt(context, selected_texts, tags))
    return validate_new_questions(raw, facts=facts, allowed_subject_types=allowed_subject_types, vocab=vocab,
                                  people=people, existing_texts=selected_texts)

"""
app.services.member_extraction
------------------------------
AI extraction of PROPOSED board member profile facts from the member's
director_profile documents. Same machinery and setting as the company
extraction (app.services.org_extraction, AI_EXTRACTION_ENABLED, off by
default): chunking, token cap, verbatim excerpt check, and re-runs never touch
confirmed, manual or rejected facts.

Extra rules for people:
- Independence: only an explicit "yes" or "no" is proposed; "unknown" answers
  are dropped (unknown is already the default).
- personality_notes: the value itself must appear verbatim in the document, so
  it can only ever be a quote, never the model's own characterisation.
- Dates: the year must appear in the excerpt.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.prompts.director_profile_extraction import SYSTEM_PROMPT, build_user_prompt
from app.db.models import BoardMember, BoardMemberFact, OrgDocument
from app.domain.board_member_profile import PROFILE_FACTS_BY_KEY, PROFILE_REGISTRY, validate_profile_value
from app.services.org_extraction import (
    ExtractionResult,
    FactRules,
    LLMCall,
    _collect_facts,
    _process_documents,
    _save_facts,
    check_enabled,
    default_llm_call,
    normalise_for_match,
    run_settings,
)


def _skip_unknown(key, value) -> bool:
    return isinstance(value, dict) and value.get("answer") == "unknown"


def _member_extra_check(key, spec, value, ex_norm, doc_norm) -> Optional[str]:
    if spec.get("generation_only") and normalise_for_match(value) not in doc_norm:
        return "notes must be a verbatim quote from the document"
    if spec["type"] == "date" and value[:4] not in ex_norm:
        return "date not stated in the excerpt"
    return None


MEMBER_FACT_RULES = FactRules(PROFILE_FACTS_BY_KEY, validate_profile_value, _member_extra_check, _skip_unknown)


def run_member_extraction(
    db: Session,
    member: BoardMember,
    *,
    llm_call: Optional[LLMCall] = None,
    max_tokens: Optional[int] = None,
    chunk_tokens: Optional[int] = None,
) -> ExtractionResult:
    """Propose profile facts from the member's director_profile documents. Flushes, doesn't commit."""
    check_enabled()
    llm_call = llm_call or default_llm_call
    cap, chunk_chars = run_settings(max_tokens, chunk_tokens)
    result = ExtractionResult(token_cap=cap)

    docs = db.execute(
        select(OrgDocument)
        .where(OrgDocument.board_member_id == member.id, OrgDocument.doc_type == "director_profile")
        .order_by(OrgDocument.uploaded_at)
    ).scalars().all()

    cands = {}
    _process_documents(
        docs, llm_call, result, cap, chunk_chars, SYSTEM_PROMPT,
        lambda doc, part, chunk: build_user_prompt(PROFILE_REGISTRY, person=member.full_name, filename=doc.filename,
                                                   part=part, text=chunk),
        lambda reply, doc, doc_norm: _collect_facts(reply, doc, doc_norm, cands, result, MEMBER_FACT_RULES),
    )
    _save_facts(db, BoardMemberFact, "board_member_id", member.id, cands, result, PROFILE_FACTS_BY_KEY)
    db.flush()
    return result

"""
app.services.org_extraction
---------------------------
AI extraction of PROPOSED organisation facts and committees from uploaded
documents. Nothing here confirms anything: a consultant reviews every proposal.

Guarded by AI_EXTRACTION_ENABLED (default false): the client hasn't yet agreed
that their documents may be sent to OpenAI.

Design:
- Documents are processed one chunk at a time (~AI_EXTRACTION_CHUNK_TOKENS
  each, split on paragraph breaks with a small overlap), most useful document
  types first.
- A run stops sending chunks once AI_EXTRACTION_MAX_TOKENS (estimated input
  tokens, ~4 characters per token) would be exceeded; skipped chunks are
  reported.
- Each reply is validated with Pydantic. A proposal is kept only if its
  source_excerpt appears verbatim in that document's text (ignoring
  whitespace, quote style and dash style), its value fits the fact registry,
  and (for numbers) the number appears in the excerpt. Committee names must
  appear in the excerpt; chair and member names must appear in the document.
- Results are merged across chunks and documents, then saved without touching
  confirmed facts, manual entries, or values a consultant already rejected.
- Document contents are never logged.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.prompts.org_profile_extraction import SYSTEM_PROMPT, build_user_prompt
from app.db.models import OrganisationFact, Organisation, OrgCommittee, OrgDocument
from app.domain.org_profile import COMMITTEE_TYPES, FACT_REGISTRY, FACTS_BY_KEY, FactValueError, validate_fact_value

log = logging.getLogger(__name__)

# Most useful first: the token cap cuts from the end.
DOC_TYPE_PRIORITY = [
    "board_structure", "committee_tor", "company_profile", "governance_policy",
    "annual_report", "public_info", "other",
]
CHARS_PER_TOKEN = 4
OVERLAP_CHARS = 400
MIN_EXCERPT_CHARS = 12
MAX_EXCERPT_CHARS = 400

LLMCall = Callable[[str, str], str]  # (system, user) -> raw text reply


class ExtractionDisabled(RuntimeError):
    pass


def ai_extraction_enabled() -> bool:
    return (os.getenv("AI_EXTRACTION_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


# ----------------------------
# Reply schema
# ----------------------------

class ProposedFactIn(BaseModel):
    key: str
    value: Any = None
    source_excerpt: str = Field(min_length=1)


class ProposedCommitteeIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    committee_type: Optional[str] = "other"
    chair_name: Optional[str] = None
    member_names: List[str] = Field(default_factory=list)
    source_excerpt: str = Field(min_length=1)


class ExtractionReply(BaseModel):
    facts: List[Dict[str, Any]] = Field(default_factory=list)
    committees: List[Dict[str, Any]] = Field(default_factory=list)


# ----------------------------
# Text helpers
# ----------------------------

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def normalise_for_match(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").translate(_QUOTES)).strip().casefold()


def chunk_text(text: str, max_chars: int) -> List[str]:
    """Split on paragraph breaks into chunks of at most ~max_chars, with a small overlap."""
    if len(text) <= max_chars:
        return [text]
    overlap = min(OVERLAP_CHARS, max_chars // 4)  # each chunk advances by at least 1/4 of max_chars
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            cut = text.rfind("\n\n", start + max_chars // 2, end)
            if cut == -1:
                cut = text.rfind("\n", start + max_chars // 2, end)
            if cut != -1:
                end = cut
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


_NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                 "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
                 "nineteen", "twenty"]


def _number_in_excerpt(n: int, excerpt_norm: str) -> bool:
    if re.search(rf"(?<!\d){n}(?!\d)", excerpt_norm):
        return True
    return n < len(_NUMBER_WORDS) and re.search(rf"\b{_NUMBER_WORDS[n]}\b", excerpt_norm) is not None


def _committee_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").casefold()).strip()


# ----------------------------
# Run
# ----------------------------

@dataclass
class _Candidate:
    value: Any
    excerpt: str
    document_id: Any
    filename: str


@dataclass
class _CommitteeCandidate:
    name: str
    committee_type: str
    chair_name: Optional[str]
    member_names: List[str]
    excerpt: str
    document_id: Any
    filename: str
    is_tor: bool


@dataclass
class ExtractionResult:
    facts_added: int = 0
    facts_updated: int = 0
    committees_added: int = 0
    committees_updated: int = 0
    documents_processed: int = 0
    chunks_processed: int = 0
    estimated_tokens_used: int = 0
    token_cap: int = 0
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    discarded: List[Dict[str, Any]] = field(default_factory=list)
    unchanged: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def default_llm_call(system: str, user: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.util.initialiseLLM import initialize_llm

    resp = initialize_llm().invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return getattr(resp, "content", resp) if isinstance(getattr(resp, "content", resp), str) else str(resp)


def _parse_reply(raw: str) -> ExtractionReply:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s.lower().startswith("json"):
            s = s[4:].strip()
    return ExtractionReply.model_validate(json.loads(s))


def run_extraction(
    db: Session,
    org: Organisation,
    *,
    llm_call: Optional[LLMCall] = None,
    max_tokens: Optional[int] = None,
    chunk_tokens: Optional[int] = None,
) -> ExtractionResult:
    """Propose facts and committees from the organisation's extracted documents. Flushes, doesn't commit."""
    check_enabled()
    llm_call = llm_call or default_llm_call
    cap, chunk_chars = run_settings(max_tokens, chunk_tokens)
    result = ExtractionResult(token_cap=cap)

    docs = db.execute(
        select(OrgDocument).where(OrgDocument.organisation_id == org.id, OrgDocument.board_member_id.is_(None))
        .order_by(OrgDocument.uploaded_at)
    ).scalars().all()
    docs = sorted(docs, key=lambda d: DOC_TYPE_PRIORITY.index(d.doc_type) if d.doc_type in DOC_TYPE_PRIORITY else 99)

    fact_cands: Dict[str, List[_Candidate]] = {}
    committee_cands: Dict[str, List[_CommitteeCandidate]] = {}

    def on_reply(reply, doc, doc_norm):
        _collect_facts(reply, doc, doc_norm, fact_cands, result, ORG_FACT_RULES)
        _collect_committees(reply, doc, doc_norm, committee_cands, result)

    _process_documents(
        docs, llm_call, result, cap, chunk_chars, SYSTEM_PROMPT,
        lambda doc, part, chunk: build_user_prompt(FACT_REGISTRY, doc_type=doc.doc_type, filename=doc.filename,
                                                   part=part, text=chunk),
        on_reply,
    )

    _save_facts(db, OrganisationFact, "organisation_id", org.id, fact_cands, result, FACTS_BY_KEY)
    _save_committees(db, org, committee_cands, result)
    db.flush()
    return result


def _process_documents(docs, llm_call: LLMCall, result: "ExtractionResult", cap: int, chunk_chars: int,
                       system_prompt: str, build_prompt, on_reply) -> None:
    """
    Shared loop: send each document's chunks (within the token cap) to the model
    and hand each parsed reply to on_reply(reply, doc, doc_norm).
    """
    for doc in docs:
        if doc.extraction_status != "done" or not (doc.extracted_text or "").strip():
            result.skipped.append({"document_id": str(doc.id), "filename": doc.filename,
                                   "reason": f"no extracted text ({doc.extraction_status})"})
            continue
        doc_norm = normalise_for_match(doc.extracted_text)
        chunks = chunk_text(doc.extracted_text, chunk_chars)
        processed_any = False
        for i, chunk in enumerate(chunks, start=1):
            part = f"part {i} of {len(chunks)}"
            user = build_prompt(doc, part, chunk)
            cost = estimate_tokens(system_prompt) + estimate_tokens(user)
            if result.estimated_tokens_used + cost > cap:
                result.skipped.append({"document_id": str(doc.id), "filename": doc.filename, "part": part,
                                       "reason": f"token cap reached ({cap} estimated input tokens per run)"})
                continue
            result.estimated_tokens_used += cost
            result.chunks_processed += 1
            processed_any = True
            try:
                reply = _parse_reply(llm_call(system_prompt, user))
            except (ValueError, ValidationError) as exc:  # json errors are ValueErrors
                result.discarded.append({"document_id": str(doc.id), "filename": doc.filename, "part": part,
                                         "reason": f"unreadable AI reply ({type(exc).__name__})"})
                continue
            except Exception as exc:
                result.skipped.append({"document_id": str(doc.id), "filename": doc.filename, "part": part,
                                       "reason": f"AI call failed ({type(exc).__name__})"})
                log.warning("Extraction call failed for document %s: %s", doc.id, type(exc).__name__)
                continue
            on_reply(reply, doc, doc_norm)
        if processed_any:
            result.documents_processed += 1


def check_enabled() -> None:
    if not ai_extraction_enabled():
        raise ExtractionDisabled(
            "AI extraction is turned off (AI_EXTRACTION_ENABLED). Enter the profile manually, or enable it once "
            "the client has agreed that their documents may be sent to the AI provider."
        )


def run_settings(max_tokens: Optional[int], chunk_tokens: Optional[int]) -> Tuple[int, int]:
    cap = max_tokens or _int_env("AI_EXTRACTION_MAX_TOKENS", 60_000)
    chunk_chars = (chunk_tokens or _int_env("AI_EXTRACTION_CHUNK_TOKENS", 6_000)) * CHARS_PER_TOKEN
    return cap, chunk_chars


def _excerpt_ok(excerpt: str, doc_norm: str) -> Tuple[bool, str]:
    ex = normalise_for_match(excerpt)
    if len(ex) < MIN_EXCERPT_CHARS:
        return False, "excerpt too short to verify"
    if len(ex) > MAX_EXCERPT_CHARS:
        return False, "excerpt too long"
    if ex not in doc_norm:
        return False, "excerpt not found in the document"
    return True, ex


@dataclass(frozen=True)
class FactRules:
    """How proposed facts are checked for one kind of profile."""
    facts_by_key: Dict[str, Dict[str, Any]]
    validate: Callable[[str, Any], Any]
    # (key, spec, value, excerpt_norm, doc_norm) -> reason to drop, or None; runs after validation
    extra_check: Optional[Callable[[str, Dict[str, Any], Any, str, str], Optional[str]]] = None
    # (key, value) -> True to silently skip (e.g. an "unknown" answer)
    skip_value: Optional[Callable[[str, Any], bool]] = None


# A number quoted from a rule or range ("between seven and eleven directors") is a limit, not an actual count
_RULE_WORDS = re.compile(r"\b(between|at least|at most|not less than|not more than|no fewer than|no more than|"
                         r"minimum|maximum|up to|shall (?:have|consist|comprise))\b")


def _org_extra_check(key, spec, value, ex_norm, doc_norm):
    if spec["type"] == "number" and not _number_in_excerpt(value, ex_norm):
        return "number not stated in the excerpt"
    if spec["type"] == "number" and _RULE_WORDS.search(ex_norm):
        return "the quote states a rule or range, not an actual number"
    return None


ORG_FACT_RULES = FactRules(FACTS_BY_KEY, validate_fact_value, _org_extra_check)


def _collect_facts(reply, doc, doc_norm, cands, result, rules: FactRules = ORG_FACT_RULES) -> None:
    for raw in reply.facts:
        try:
            item = ProposedFactIn.model_validate(raw)
        except ValidationError:
            result.discarded.append({"filename": doc.filename, "reason": "fact missing key or excerpt"})
            continue
        spec = rules.facts_by_key.get(item.key)
        what = {"key": item.key, "label": spec["label"] if spec else item.key, "filename": doc.filename}
        if spec is None:
            result.discarded.append({**what, "reason": "unknown fact key"})
            continue
        if item.value is None:
            continue  # the model reported an unknown: nothing to propose
        ok, ex_norm = _excerpt_ok(item.source_excerpt, doc_norm)
        if not ok:
            result.discarded.append({**what, "reason": ex_norm})
            continue
        try:
            value = rules.validate(item.key, item.value)
        except FactValueError as exc:
            result.discarded.append({**what, "reason": f"value doesn't fit: {exc}"})
            continue
        if rules.skip_value and rules.skip_value(item.key, value):
            continue
        reason = rules.extra_check(item.key, spec, value, ex_norm, doc_norm) if rules.extra_check else None
        if reason:
            result.discarded.append({**what, "reason": reason})
            continue
        cands.setdefault(item.key, []).append(_Candidate(value, item.source_excerpt.strip(), doc.id, doc.filename))


def _collect_committees(reply, doc, doc_norm, cands, result) -> None:
    for raw in reply.committees:
        try:
            item = ProposedCommitteeIn.model_validate(raw)
        except ValidationError:
            result.discarded.append({"filename": doc.filename, "reason": "committee missing name or excerpt"})
            continue
        what = {"committee": item.name, "filename": doc.filename}
        ok, ex_norm = _excerpt_ok(item.source_excerpt, doc_norm)
        if not ok:
            result.discarded.append({**what, "reason": ex_norm})
            continue
        if normalise_for_match(item.name) not in doc_norm:
            result.discarded.append({**what, "reason": "committee name not found in the document"})
            continue
        names, dropped = [], []
        for n in item.member_names:
            n = (n or "").strip()
            if not n:
                continue
            (names if normalise_for_match(n) in doc_norm else dropped).append(n)
        chair = (item.chair_name or "").strip() or None
        if chair and normalise_for_match(chair) not in doc_norm:
            dropped.append(chair)
            chair = None
        for n in dropped:
            result.discarded.append({**what, "reason": f"name {n!r} not found in the document"})
        ctype = (item.committee_type or "other").strip().lower()
        cands.setdefault(_committee_key(item.name), []).append(_CommitteeCandidate(
            name=item.name.strip(), committee_type=ctype if ctype in COMMITTEE_TYPES else "other",
            chair_name=chair, member_names=names, excerpt=item.source_excerpt.strip(),
            document_id=doc.id, filename=doc.filename, is_tor=doc.doc_type == "committee_tor",
        ))


def _same_list_item(a: str, b: str) -> bool:
    """Same text ignoring case and spacing, or one is the bracketed short form of the other ("NAICOM" in "... (NAICOM)")."""
    na, nb = normalise_for_match(a), normalise_for_match(b)
    return na == nb or f"({na})" in nb or f"({nb})" in na


def _value_text(v: Any) -> str:
    if isinstance(v, str):
        return f"“{v}”"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k.replace('_', ' ')}: {x}" for k, x in v.items())
    return str(v)


def _merge_fact(key: str, cands: List[_Candidate], facts_by_key=FACTS_BY_KEY) -> Tuple[Any, _Candidate, Optional[str]]:
    """First candidate (most useful document first) wins; lists are unioned. Returns (value, primary, note)."""
    primary = cands[0]
    if facts_by_key[key]["type"] == "list":
        merged: List[str] = []
        for c in cands:
            for x in c.value:
                same = next((i for i, y in enumerate(merged) if _same_list_item(x, y)), None)
                if same is None:
                    merged.append(x)
                elif len(x) > len(merged[same]):  # keep the fuller form, e.g. "National Insurance Commission (NAICOM)"
                    merged[same] = x
        others = sorted({c.filename for c in cands[1:] if c.filename != primary.filename})
        return merged, primary, ("Also found in: " + ", ".join(others)) if others else None
    differing = [c for c in cands[1:] if c.value != primary.value]
    note = None
    if differing:
        note = "Other values found: " + "; ".join(f"{_value_text(c.value)} ({c.filename})" for c in differing)
    return primary.value, primary, note


def _save_facts(db: Session, model, owner_column: str, owner_id, cands: Dict[str, List[_Candidate]],
                result: ExtractionResult, facts_by_key) -> None:
    existing = db.execute(select(model).where(getattr(model, owner_column) == owner_id)).scalars().all()
    for key, items in cands.items():
        value, primary, note = _merge_fact(key, items, facts_by_key)
        same_key = [f for f in existing if f.key == key]
        confirmed = next((f for f in same_key if f.status == "confirmed"), None)
        proposed = next((f for f in same_key if f.status == "proposed"), None)

        if any(f.origin == "manual" and f.status != "rejected" for f in same_key):
            result.unchanged.append({"key": key, "reason": "a manual entry exists"})
            continue
        if confirmed is not None and confirmed.value == value:
            result.unchanged.append({"key": key, "reason": "matches the confirmed value"})
            continue
        if any(f.status == "rejected" and f.value == value for f in same_key):
            result.unchanged.append({"key": key, "reason": "this value was rejected before"})
            continue

        if proposed is not None:  # an earlier AI proposal: refresh it
            proposed.value, proposed.source_excerpt, proposed.source_document_id, proposed.note = (
                value, primary.excerpt, primary.document_id, note
            )
            result.facts_updated += 1
        else:
            db.add(model(
                **{owner_column: owner_id}, key=key, value=value, source="client", status="proposed",
                origin="ai_extraction", source_document_id=primary.document_id, source_excerpt=primary.excerpt,
                note=note,
            ))
            result.facts_added += 1


def _save_committees(db, org, cands: Dict[str, List[_CommitteeCandidate]], result: ExtractionResult) -> None:
    existing = db.execute(select(OrgCommittee).where(OrgCommittee.organisation_id == org.id)).scalars().all()
    by_key: Dict[str, List[OrgCommittee]] = {}
    for c in existing:
        by_key.setdefault(_committee_key(c.name), []).append(c)

    for key, items in cands.items():
        primary = items[0]
        members: List[str] = []
        for c in items:
            members += [m for m in c.member_names if m not in members]
        chair = next((c.chair_name for c in items if c.chair_name), None)
        tor = next((c.document_id for c in items if c.is_tor), None)

        matches = by_key.get(key, [])
        if any(m.status == "confirmed" or m.origin == "manual" for m in matches):
            result.unchanged.append({"committee": primary.name, "reason": "confirmed or manual entry exists"})
            continue
        if any(m.status == "rejected" for m in matches):
            result.unchanged.append({"committee": primary.name, "reason": "rejected before"})
            continue
        if matches:
            m = matches[0]
            m.name, m.committee_type, m.chair_name, m.member_names = primary.name, primary.committee_type, chair, members
            m.source_document_id, m.source_excerpt = primary.document_id, primary.excerpt
            m.terms_of_reference_document_id = tor or m.terms_of_reference_document_id
            result.committees_updated += 1
        else:
            db.add(OrgCommittee(
                organisation_id=org.id, name=primary.name, committee_type=primary.committee_type,
                chair_name=chair, member_names=members, terms_of_reference_document_id=tor,
                source="client", status="proposed", origin="ai_extraction",
                source_document_id=primary.document_id, source_excerpt=primary.excerpt,
            ))
            result.committees_added += 1

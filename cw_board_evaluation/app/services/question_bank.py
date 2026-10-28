"""
app.services.question_bank
--------------------------
Database helpers for the question bank: create, edit (a new version when the
item is approved), approve, retire, governance clause links, loading a
fixture, and the dicts the API returns.

Versioning: only the latest version of a code can be edited, approved or
retired. Editing a draft changes it in place; editing an approved item
creates version n+1 as a draft and leaves version n untouched for audit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    GovernanceClause,
    QuestionBankItem,
    QuestionBankItemClause,
    QuestionBankItemSubjectType,
)
from app.domain.question_bank import STATUSES, BankItemError, validate_item
from app.domain.question_rules import describe_rule, fact_label
from app.services.taxonomy import validate_tag_codes

CONTENT_FIELDS = (
    "code", "text", "answer_type", "options", "scale", "subject_types", "subject_binding", "respondent_rule",
    "activation_rule", "theme_code", "evidence_source_code", "known_from", "known_from_behaviour", "placeholders",
    "guidance", "source_refs", "tag_notes", "weight", "sort_order", "priority", "review_notes", "expected_answer",
)


class BankConflict(ValueError):
    """The action isn't allowed in the item's current state (HTTP 409)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------
# Reading
# ----------------------------

def item_content(item: QuestionBankItem) -> Dict[str, Any]:
    out = {f: getattr(item, f) for f in CONTENT_FIELDS if f != "subject_types"}
    out["subject_types"] = item.subject_type_codes
    return out


def versions_of(db: Session, code: str) -> List[QuestionBankItem]:
    return list(db.execute(
        select(QuestionBankItem).where(QuestionBankItem.code == code).order_by(QuestionBankItem.version)
    ).scalars().all())


def latest_version(db: Session, code: str) -> Optional[QuestionBankItem]:
    return db.execute(
        select(QuestionBankItem).where(QuestionBankItem.code == code).order_by(QuestionBankItem.version.desc()).limit(1)
    ).scalars().first()


def list_items(db: Session, *, subject_type: Optional[str] = None, theme: Optional[str] = None,
               evidence_source: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
               all_versions: bool = False) -> List[QuestionBankItem]:
    """Items matching the filters; by default only the latest version of each code."""
    stmt = select(QuestionBankItem)
    if not all_versions:
        latest = (select(QuestionBankItem.code, func.max(QuestionBankItem.version).label("v"))
                  .group_by(QuestionBankItem.code).subquery())
        stmt = stmt.join(latest, (latest.c.code == QuestionBankItem.code) & (latest.c.v == QuestionBankItem.version))
    if subject_type:
        stmt = stmt.where(QuestionBankItem.subject_type_links.any(QuestionBankItemSubjectType.subject_type_code == subject_type))
    if theme:
        stmt = stmt.where(QuestionBankItem.theme_code == theme)
    if evidence_source:
        stmt = stmt.where(QuestionBankItem.evidence_source_code == evidence_source)
    if status:
        stmt = stmt.where(QuestionBankItem.status == status)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(QuestionBankItem.text.ilike(like), QuestionBankItem.code.ilike(like),
                              QuestionBankItem.guidance.ilike(like)))
    stmt = stmt.order_by(QuestionBankItem.sort_order, QuestionBankItem.code, QuestionBankItem.version)
    return list(db.execute(stmt).scalars().all())


# ----------------------------
# Validation and writes
# ----------------------------

def validate_content(db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
    """Domain validation plus a check that the tag codes exist. Raises BankItemError."""
    errors: List[str] = []
    try:
        norm = validate_item(data)
    except BankItemError as e:
        errors.extend(e.errors)
        norm = None
    for field in ("theme_code", "evidence_source_code"):
        if not data.get(field):
            errors.append(f"{field} is required.")
    errors.extend(validate_tag_codes(
        db, theme_codes=[data.get("theme_code")], evidence_source_codes=[data.get("evidence_source_code")],
        subject_type_codes=data.get("subject_types") or [],
    ))
    if errors:
        raise BankItemError(errors)
    norm["theme_code"] = data["theme_code"]
    norm["evidence_source_code"] = data["evidence_source_code"]
    return norm


def _apply(item: QuestionBankItem, norm: Dict[str, Any]) -> None:
    for f in CONTENT_FIELDS:
        if f not in ("code", "subject_types"):
            setattr(item, f, norm[f])
    wanted = norm["subject_types"]
    item.subject_type_links = [link for link in item.subject_type_links if link.subject_type_code in wanted]
    have = set(item.subject_type_codes)
    for code in wanted:
        if code not in have:
            item.subject_type_links.append(QuestionBankItemSubjectType(subject_type_code=code))


def create_item(db: Session, data: Dict[str, Any]) -> QuestionBankItem:
    norm = validate_content(db, data)
    if latest_version(db, norm["code"]) is not None:
        raise BankItemError([f"Code {norm['code']} already exists; edit it to make a new version."])
    item = QuestionBankItem(code=norm["code"], version=1, status="draft")
    _apply(item, norm)
    db.add(item)
    db.flush()
    return item


def _ensure_latest(db: Session, item: QuestionBankItem, action: str) -> None:
    latest = latest_version(db, item.code)
    if latest is not None and latest.id != item.id:
        raise BankConflict(f"Only the latest version (v{latest.version}) of {item.code} can be {action}.")


def update_item(db: Session, item: QuestionBankItem, changes: Dict[str, Any]) -> Tuple[QuestionBankItem, bool]:
    """
    Apply changes. A draft is changed in place; an approved item gets a new
    draft version. Returns (the item now holding the changes, whether it is a new version).
    """
    if item.status == "retired":
        raise BankConflict(f"{item.code} v{item.version} is retired and can't be edited.")
    _ensure_latest(db, item, "edited")
    if "code" in changes and str(changes["code"] or "").strip().upper() != item.code:
        raise BankItemError(["The code can't be changed; create a new item instead."])
    norm = validate_content(db, {**item_content(item), **changes, "code": item.code})
    if item.status == "draft":
        _apply(item, norm)
        db.flush()
        return item, False
    new = QuestionBankItem(code=item.code, version=item.version + 1, status="draft")
    _apply(new, norm)
    new.clause_links = [QuestionBankItemClause(clause_id=link.clause_id, status=link.status) for link in item.clause_links]
    db.add(new)
    db.flush()
    return new, True


def approve_item(db: Session, item: QuestionBankItem) -> QuestionBankItem:
    if item.status != "draft":
        raise BankConflict(f"{item.code} v{item.version} is {item.status}; only drafts can be approved.")
    _ensure_latest(db, item, "approved")
    validate_content(db, item_content(item))
    item.status = "approved"
    item.approved_at = _now()
    db.flush()
    return item


def retire_item(db: Session, item: QuestionBankItem) -> QuestionBankItem:
    if item.status == "retired":
        raise BankConflict(f"{item.code} v{item.version} is already retired.")
    _ensure_latest(db, item, "retired")
    item.status = "retired"
    db.flush()
    return item


# ----------------------------
# Governance clause links
# ----------------------------

def find_clause(db: Session, code: str, reference: str) -> Optional[GovernanceClause]:
    return db.execute(
        select(GovernanceClause).where(GovernanceClause.code == code, GovernanceClause.reference == reference)
    ).scalars().first()


def link_clause(db: Session, item: QuestionBankItem, clause: GovernanceClause, status: str = "confirmed") -> QuestionBankItemClause:
    link = next((x for x in item.clause_links if x.clause_id == clause.id), None)
    if link is None:
        link = QuestionBankItemClause(clause_id=clause.id, status=status)
        item.clause_links.append(link)
    else:
        link.status = status
    db.flush()
    return link


def clause_link(item: QuestionBankItem, clause_id) -> Optional[QuestionBankItemClause]:
    return next((x for x in item.clause_links if str(x.clause_id) == str(clause_id)), None)


def remove_clause_link(db: Session, item: QuestionBankItem, link: QuestionBankItemClause) -> None:
    item.clause_links.remove(link)
    db.flush()


# ----------------------------
# API shape
# ----------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def clause_dict(link: QuestionBankItemClause) -> Dict[str, Any]:
    c = link.clause
    return {
        "clause_id": str(link.clause_id),
        "code": c.code,
        "reference": c.reference,
        "heading": c.heading,
        "text": c.text,
        "status": link.status,
    }


def item_dict(item: QuestionBankItem) -> Dict[str, Any]:
    links = sorted(item.clause_links, key=lambda x: (x.clause.code, x.clause.sort_order))
    return {
        "id": str(item.id),
        "code": item.code,
        "version": item.version,
        "status": item.status,
        "text": item.text,
        "answer_type": item.answer_type,
        "options": item.options,
        "scale": item.scale,
        "subject_types": item.subject_type_codes,
        "subject_binding": item.subject_binding,
        "respondent_rule": item.respondent_rule,
        "respondent_rule_text": describe_rule(item.respondent_rule),
        "activation_rule": item.activation_rule,
        "activation_rule_text": describe_rule(item.activation_rule),
        "theme_code": item.theme_code,
        "evidence_source_code": item.evidence_source_code,
        "known_from": item.known_from,
        "known_from_label": fact_label(item.known_from) if item.known_from else None,
        "known_from_behaviour": item.known_from_behaviour,
        "expected_answer": item.expected_answer,
        "placeholders": item.placeholders or [],
        "templated": bool(item.placeholders),
        "guidance": item.guidance,
        "source_refs": item.source_refs or [],
        "tag_notes": item.tag_notes or {},
        "weight": item.weight,
        "sort_order": item.sort_order,
        "priority": item.priority,
        "review_notes": item.review_notes,
        "clauses": [clause_dict(x) for x in links],
        "approved_at": _iso(item.approved_at),
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


# ----------------------------
# Loading a fixture
# ----------------------------

FIXTURE_FORMAT = "cw-question-bank"


def load_fixture(db: Session, fixture: Dict[str, Any], *, update_drafts: bool = False) -> Dict[str, Any]:
    """
    Load a bank fixture idempotently by (code, version). An item already in the
    database is left alone (or, with update_drafts, refreshed if still a draft),
    so consultants' edits are never overwritten. Every item is validated
    (content, rules and tag codes) and its governance references resolved;
    anything that can't load is reported, not guessed. Flushes but does not commit.
    """
    if fixture.get("format") != FIXTURE_FORMAT:
        raise ValueError(f"Not a question bank fixture (format should be {FIXTURE_FORMAT!r}).")
    summary: Dict[str, Any] = {"created": [], "updated": [], "unchanged": [], "errors": [], "unresolved_clauses": []}
    seen = set()
    for raw in fixture.get("items") or []:
        code = str(raw.get("code") or "").strip().upper()
        version = raw.get("version", 1)
        label = f"{code or '(no code)'} v{version}"
        problems: List[str] = []
        if (code, version) in seen:
            problems.append("appears more than once in the fixture")
        seen.add((code, version))
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            problems.append("version must be a whole number >= 1")
        status = raw.get("status", "draft")
        if status not in STATUSES:
            problems.append(f"status must be one of: {', '.join(STATUSES)}")
        try:
            norm = validate_content(db, raw)
        except BankItemError as e:
            problems.extend(e.errors)
        if problems:
            summary["errors"].append({"item": label, "errors": problems})
            continue

        existing = db.execute(
            select(QuestionBankItem).where(QuestionBankItem.code == code, QuestionBankItem.version == version)
        ).scalars().first()
        if existing is not None and not (update_drafts and existing.status == "draft" and status == "draft"):
            summary["unchanged"].append(label)
            continue
        item = existing or QuestionBankItem(code=code, version=version)
        item.status = status
        if status == "approved" and item.approved_at is None:
            item.approved_at = _now()
        _apply(item, norm)
        if existing is None:
            db.add(item)
        for ref in raw.get("governance_refs") or []:
            clause = find_clause(db, ref.get("code", ""), ref.get("reference", ""))
            if clause is None:
                summary["unresolved_clauses"].append({"item": label, "code": ref.get("code"), "reference": ref.get("reference")})
                continue
            if not any(x.clause_id == clause.id for x in item.clause_links):
                item.clause_links.append(QuestionBankItemClause(clause_id=clause.id, status=ref.get("status", "suggested")))
        db.flush()
        summary["updated" if existing is not None else "created"].append(label)
    return summary


def summary_counts(summary: Dict[str, Any]) -> Dict[str, int]:
    return {k: len(v) for k, v in summary.items() if isinstance(v, list)}

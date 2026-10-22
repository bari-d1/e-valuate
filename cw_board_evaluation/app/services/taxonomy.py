"""
app.services.taxonomy
---------------------
Database helpers for the tagging vocabulary (subject types, themes, evidence
sources): idempotent seeding and code validation.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceSource, SubjectType, Theme
from app.domain.taxonomy import EVIDENCE_SOURCES, SUBJECT_TYPES, THEMES


def seed_taxonomy(db: Session) -> Dict[str, int]:
    """
    Insert any missing subject types, themes and evidence sources.

    Existing rows are left untouched (theme names are client-editable data).
    Returns counts of rows created per table. Does not commit.
    """
    created = {"subject_types": 0, "themes": 0, "evidence_sources": 0}
    specs = (
        ("subject_types", SubjectType, SUBJECT_TYPES),
        ("themes", Theme, THEMES),
        ("evidence_sources", EvidenceSource, EVIDENCE_SOURCES),
    )
    for key, model, rows in specs:
        existing = set(db.execute(select(model.code)).scalars().all())
        for i, spec in enumerate(rows):
            if spec["code"] in existing:
                continue
            values = {"sort_order": (i + 1) * 10, "description": None, **spec}
            if hasattr(model, "active"):
                values.setdefault("active", 1)
            db.add(model(**values))
            created[key] += 1
    db.flush()
    return created


def normalize_code(code: Optional[str]) -> Optional[str]:
    c = (code or "").strip().upper()
    return c or None


def _active_codes(db: Session, model) -> set:
    stmt = select(model.code)
    if hasattr(model, "active"):
        stmt = stmt.where(model.active == 1)
    return set(db.execute(stmt).scalars().all())


def validate_tag_codes(
    db: Session,
    *,
    theme_codes: Iterable[Optional[str]] = (),
    evidence_source_codes: Iterable[Optional[str]] = (),
    subject_type_codes: Iterable[Optional[str]] = (),
) -> List[str]:
    """
    Return human-readable errors for codes that don't exist (or are inactive).
    Empty list means all codes are valid. Codes should already be normalized.
    """
    errors: List[str] = []
    checks = (
        ("theme_code", Theme, theme_codes),
        ("evidence_source_code", EvidenceSource, evidence_source_codes),
        ("subject_type_codes", SubjectType, subject_type_codes),
    )
    for field, model, codes in checks:
        wanted = sorted({c for c in codes if c})
        if not wanted:
            continue
        known = _active_codes(db, model)
        unknown = [c for c in wanted if c not in known]
        if unknown:
            errors.append(f"Unknown {field}: {', '.join(unknown)}.")
    return errors

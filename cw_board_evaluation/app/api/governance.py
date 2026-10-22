"""
app.api.governance
------------------
Governance code library (read-only).

Endpoints:
- GET /api/v1/governance-codes
- GET /api/v1/governance-codes/{code}
- GET /api/v1/governance-codes/{code}/clauses?subject=&theme=&q=
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    GovernanceClause,
    GovernanceClauseSubjectType,
    GovernanceCode,
    SectorCodeDefault,
    SubjectType,
    Theme,
)
from app.db.session import get_db

router = APIRouter()

_STATUS_ORDER = {"current": 0, "historical": 1, "superseded": 2}


def _get_code_or_404(db: Session, code: str) -> GovernanceCode:
    gc = db.get(GovernanceCode, code)
    if not gc:
        raise HTTPException(status_code=404, detail=f"Governance code not found: {code}")
    return gc


def _code_dict(gc: GovernanceCode, clause_count: int) -> Dict[str, Any]:
    return {
        "code": gc.code,
        "title": gc.title,
        "issuer": gc.issuer,
        "jurisdiction": gc.jurisdiction,
        "sector": gc.sector,
        "version": gc.version,
        "issued_date": gc.issued_date.isoformat() if gc.issued_date else None,
        "effective_date": gc.effective_date.isoformat() if gc.effective_date else None,
        "status": gc.status,
        "supplements_code": gc.supplements_code,
        "source_filename": gc.source_filename,
        "clauses_loaded": bool(gc.clauses_loaded),
        "clause_count": clause_count,
        "notes": gc.notes,
    }


def _clause_counts(db: Session) -> Dict[str, int]:
    rows = db.execute(select(GovernanceClause.code, func.count()).group_by(GovernanceClause.code)).all()
    return {code: n for code, n in rows}


@router.get("/governance-codes")
def list_governance_codes(db: Session = Depends(get_db)) -> Dict[str, Any]:
    counts = _clause_counts(db)
    codes = db.execute(select(GovernanceCode)).scalars().all()
    codes = sorted(codes, key=lambda c: (_STATUS_ORDER.get(c.status, 9), c.supplements_code is not None, c.code))
    items = [_code_dict(c, counts.get(c.code, 0)) for c in codes]
    return {"count": len(items), "items": items}


@router.get("/governance-codes/{code}")
def get_governance_code(code: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    gc = _get_code_or_404(db, code)
    count = _clause_counts(db).get(code, 0)
    by_level = dict(
        db.execute(
            select(GovernanceClause.level, func.count()).where(GovernanceClause.code == code).group_by(GovernanceClause.level)
        ).all()
    )
    supplemented_by = db.execute(
        select(GovernanceCode.code).where(GovernanceCode.supplements_code == code).order_by(GovernanceCode.code)
    ).scalars().all()
    defaults = db.execute(
        select(SectorCodeDefault.sector, SectorCodeDefault.sub_type)
        .where(SectorCodeDefault.code == code)
        .order_by(SectorCodeDefault.sector, SectorCodeDefault.sub_type)
    ).all()
    return {
        **_code_dict(gc, count),
        "clause_counts_by_level": by_level,
        "supplemented_by": list(supplemented_by),
        "sector_defaults": [{"sector": s, "sub_type": t} for s, t in defaults],
    }


@router.get("/governance-codes/{code}/clauses")
def list_governance_clauses(
    code: str,
    subject: Optional[str] = None,
    theme: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Clauses in document order as a flat list. Each item carries its parent,
    depth and ancestor path, so the hierarchy survives filtering.
    Filters: subject (subject type code), theme (theme code), q (text search
    in reference, heading and text).
    """
    _get_code_or_404(db, code)

    subject_code = (subject or "").strip().upper() or None
    theme_code = (theme or "").strip().upper() or None
    if subject_code and not db.get(SubjectType, subject_code):
        raise HTTPException(status_code=400, detail=f"Unknown subject type: {subject_code}")
    if theme_code and not db.get(Theme, theme_code):
        raise HTTPException(status_code=400, detail=f"Unknown theme: {theme_code}")

    all_clauses = db.execute(
        select(GovernanceClause).where(GovernanceClause.code == code).order_by(GovernanceClause.sort_order)
    ).scalars().all()
    by_id = {c.id: c for c in all_clauses}

    cited_ids = {c.cites_clause_id for c in all_clauses if c.cites_clause_id}
    cited = {}
    if cited_ids:
        cited = {c.id: c for c in db.execute(select(GovernanceClause).where(GovernanceClause.id.in_(cited_ids))).scalars().all()}

    stmt = select(GovernanceClause.id).where(GovernanceClause.code == code)
    if subject_code:
        stmt = stmt.join(GovernanceClauseSubjectType, GovernanceClauseSubjectType.clause_id == GovernanceClause.id).where(
            GovernanceClauseSubjectType.subject_type_code == subject_code
        )
    if theme_code:
        stmt = stmt.where(GovernanceClause.theme_code == theme_code)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            GovernanceClause.reference.ilike(like) | GovernanceClause.heading.ilike(like) | GovernanceClause.text.ilike(like)
        )
    wanted = set(db.execute(stmt).scalars().all())

    def ancestors(c: GovernanceClause) -> List[GovernanceClause]:
        chain = []
        p = by_id.get(c.parent_id)
        while p is not None:
            chain.append(p)
            p = by_id.get(p.parent_id)
        return list(reversed(chain))

    items = []
    for c in all_clauses:
        if c.id not in wanted:
            continue
        path = ancestors(c)
        target = cited.get(c.cites_clause_id)
        items.append({
            "clause_id": str(c.id),
            "code": c.code,
            "reference": c.reference,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "parent_reference": path[-1].reference if path else None,
            "depth": len(path),
            "path": [{"reference": a.reference, "heading": a.heading} for a in path],
            "level": c.level,
            "heading": c.heading,
            "text": c.text,
            "sort_order": c.sort_order,
            "theme_code": c.theme_code,
            "subject_type_codes": c.subject_type_codes,
            "cites": (
                {"clause_id": str(target.id), "code": target.code, "reference": target.reference}
                if target else None
            ),
        })

    return {
        "code": code,
        "filters": {"subject": subject_code, "theme": theme_code, "q": (q or "").strip() or None},
        "count": len(items),
        "items": items,
    }

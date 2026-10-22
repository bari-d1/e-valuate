"""
app.services.governance
-----------------------
Database helpers for the governance code library.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GovernanceClause, GovernanceCode
from app.domain.governance import GOVERNANCE_CODES

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "reference" / "governance"


def seed_governance_codes(db: Session) -> Dict[str, int]:
    """
    Register any missing governance codes (metadata only). Existing rows are
    left untouched: a new edition is a new code, never an overwrite.
    Flushes but does not commit.
    """
    existing = set(db.execute(select(GovernanceCode.code)).scalars().all())
    created = 0
    for spec in GOVERNANCE_CODES:  # base code first (supplements_code FK)
        if spec["code"] in existing:
            continue
        db.add(GovernanceCode(jurisdiction="NG", clauses_loaded=False, **spec))
        db.flush()
        created += 1
    return {"governance_codes": created}


def read_fixture(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_clause_fixtures(db: Session, fixtures: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Load clause fixtures idempotently, keyed by (code, reference):
    existing clauses are updated in place (ids stay stable), new ones created,
    and clauses no longer in a fixture removed. Parents and cross-code
    citations are resolved after all fixtures are in, so order doesn't matter.
    Sets governance_codes.clauses_loaded. Flushes but does not commit.
    """
    fixtures = list(fixtures)
    summary: Dict[str, Any] = {"codes": {}, "unresolved_citations": []}

    by_code: Dict[str, Dict[str, GovernanceClause]] = {}
    for fx in fixtures:
        code = fx["code"]
        gc = db.get(GovernanceCode, code)
        if gc is None:
            raise ValueError(f"Governance code {code} is not registered; run scripts/seed_reference_data.py first.")

        existing = {
            c.reference: c
            for c in db.execute(select(GovernanceClause).where(GovernanceClause.code == code)).scalars().all()
        }
        wanted = {row["reference"] for row in fx["clauses"]}
        created = updated = 0
        for row in fx["clauses"]:
            c = existing.get(row["reference"])
            if c is None:
                c = GovernanceClause(code=code, reference=row["reference"])
                db.add(c)
                existing[row["reference"]] = c
                created += 1
            else:
                updated += 1
            c.level = row["level"]
            c.heading = row.get("heading")
            c.text = row.get("text") or ""
            c.sort_order = int(row["sort_order"])
        removed = 0
        for ref, c in list(existing.items()):
            if ref not in wanted:
                db.delete(c)
                del existing[ref]
                removed += 1
        db.flush()
        by_code[code] = existing
        summary["codes"][code] = {"created": created, "updated": updated, "removed": removed}

    def lookup(code: str, ref: str) -> Optional[GovernanceClause]:
        if code not in by_code:
            clauses = db.execute(select(GovernanceClause).where(GovernanceClause.code == code)).scalars().all()
            by_code[code] = {c.reference: c for c in clauses}
        return by_code[code].get(ref)

    for fx in fixtures:
        code = fx["code"]
        for row in fx["clauses"]:
            c = by_code[code][row["reference"]]
            parent_ref = row.get("parent_reference")
            c.parent_id = by_code[code][parent_ref].id if parent_ref else None
            target_id = None
            if row.get("cites"):
                target_code, target_ref = row["cites"].split(":", 1)
                target = lookup(target_code, target_ref)
                if target is None:
                    summary["unresolved_citations"].append({"code": code, "reference": row["reference"], "cites": row["cites"]})
                else:
                    target_id = target.id
            c.cites_clause_id = target_id
        db.get(GovernanceCode, code).clauses_loaded = True
    db.flush()
    return summary


def fixture_paths(codes: Optional[List[str]] = None) -> List[Path]:
    paths = sorted(FIXTURE_DIR.glob("*.json"))
    if codes:
        paths = [p for p in paths if p.stem in set(codes)]
    return paths

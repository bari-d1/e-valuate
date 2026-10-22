"""
app.services.governance
-----------------------
Database helpers for the governance code library.
"""

from __future__ import annotations

from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GovernanceCode
from app.domain.governance import GOVERNANCE_CODES


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

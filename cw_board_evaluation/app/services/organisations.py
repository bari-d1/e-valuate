"""
app.services.organisations
--------------------------
Organisations and the legacy evaluation columns that mirror them.

Evaluation.tenant_name, sector and regulators are still read by analytics,
reports, exports, the portal and emails. Rather than changing those readers,
they are kept in sync from the evaluation's organisation.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evaluation, Organisation, OrganisationFact


def confirmed_regulators(db: Session, organisation_id) -> Optional[List[str]]:
    """Regulators from the organisation's confirmed `regulator` fact, or None if there isn't one."""
    fact = db.execute(
        select(OrganisationFact).where(
            OrganisationFact.organisation_id == organisation_id,
            OrganisationFact.key == "regulator",
            OrganisationFact.status == "confirmed",
        )
    ).scalar_one_or_none()
    if fact is None or not isinstance(fact.value, list):
        return None
    return [str(x) for x in fact.value]


def sync_evaluation_from_organisation(db: Session, ev: Evaluation, org: Organisation) -> None:
    """
    Copy the organisation's name and sector onto the evaluation's legacy
    columns. Regulators are copied only when the organisation has a confirmed
    `regulator` fact, so regulators entered on old evaluations aren't wiped.
    """
    ev.organisation_id = org.id
    ev.tenant_name = org.name
    ev.sector = org.sector_key or ev.sector or ""
    regs = confirmed_regulators(db, org.id)
    if regs is not None:
        ev.regulators = {"items": regs}


def resync_organisation_evaluations(db: Session, org: Organisation) -> int:
    """Re-apply the organisation's name/sector/regulators to all its evaluations. Returns the count."""
    evals = db.execute(select(Evaluation).where(Evaluation.organisation_id == org.id)).scalars().all()
    for ev in evals:
        sync_evaluation_from_organisation(db, ev, org)
    return len(evals)

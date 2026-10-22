"""
app.services.organisations
--------------------------
Organisations and the legacy evaluation columns that mirror them.

Evaluation.tenant_name, sector and regulators are still read by analytics,
reports, exports, the portal and emails. Rather than changing those readers,
they are kept in sync from the evaluation's organisation.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Evaluation,
    EvaluationGovernanceCode,
    EvaluationScopeSubjectType,
    GovernanceCode,
    Organisation,
    OrganisationFact,
    OrganisationGovernanceCode,
    SectorCodeDefault,
    SubjectType,
)
from app.domain.governance import normalize_sector
from app.services.governance import default_codes_for_sector


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
    """
    Re-apply the organisation's name/sector/regulators to its evaluations that
    aren't closed (closed evaluations keep what they were run with). Returns the count.
    """
    evals = db.execute(
        select(Evaluation).where(Evaluation.organisation_id == org.id, Evaluation.status != "closed")
    ).scalars().all()
    for ev in evals:
        sync_evaluation_from_organisation(db, ev, org)
    return len(evals)


# ----------------------------
# Governance codes
# ----------------------------

class UnknownGovernanceCode(ValueError):
    pass


def sector_default_codes(db: Session, sector_key: Optional[str], sub_type: Optional[str]) -> List[str]:
    """Default codes for a sector key (a sub-type uses its own list)."""
    if not sector_key:
        return []
    stmt = select(SectorCodeDefault.code).where(SectorCodeDefault.sector == sector_key)
    stmt = (stmt.where(SectorCodeDefault.sub_type == sub_type) if sub_type
            else stmt.where(SectorCodeDefault.sub_type.is_(None)))
    return sorted(db.execute(stmt).scalars().all())


def link_sector_defaults(db: Session, org: Organisation) -> List[str]:
    """
    Link the organisation's sector defaults (source = sector_default).
    Previous sector-default links that no longer apply are removed; manual
    links are kept. Returns the default codes now linked.
    """
    wanted = set(sector_default_codes(db, org.sector_key, org.sector_sub_type))
    existing = {r.code: r for r in db.execute(
        select(OrganisationGovernanceCode).where(OrganisationGovernanceCode.organisation_id == org.id)
    ).scalars().all()}
    for code, row in existing.items():
        if row.source == "sector_default" and code not in wanted:
            db.delete(row)
    for code in wanted:
        if code not in existing:
            db.add(OrganisationGovernanceCode(organisation_id=org.id, code=code, source="sector_default"))
    db.flush()
    return sorted(wanted)


def organisation_codes(db: Session, org: Organisation) -> List[OrganisationGovernanceCode]:
    return db.execute(
        select(OrganisationGovernanceCode).where(OrganisationGovernanceCode.organisation_id == org.id)
        .order_by(OrganisationGovernanceCode.code)
    ).scalars().all()


def set_organisation_codes(db: Session, org: Organisation, codes: Iterable[str]) -> List[OrganisationGovernanceCode]:
    """
    Replace the organisation's codes with `codes`. Codes that were sector
    defaults keep that source; anything newly added is manual.
    """
    wanted = sorted({(c or "").strip() for c in codes if (c or "").strip()})
    known = set(db.execute(select(GovernanceCode.code).where(GovernanceCode.code.in_(wanted))).scalars().all())
    unknown = [c for c in wanted if c not in known]
    if unknown:
        raise UnknownGovernanceCode(f"Unknown governance code(s): {', '.join(unknown)}.")
    existing = {r.code: r for r in organisation_codes(db, org)}
    for code, row in existing.items():
        if code not in wanted:
            db.delete(row)
    for code in wanted:
        if code not in existing:
            db.add(OrganisationGovernanceCode(organisation_id=org.id, code=code, source="manual"))
    db.flush()
    return organisation_codes(db, org)


def apply_evaluation_code_defaults(db: Session, ev: Evaluation) -> Dict[str, object]:
    """
    Set the evaluation's governance codes from its organisation's codes, or,
    without an organisation, from the sector defaults for Evaluation.sector.
    Existing manual codes on the evaluation are kept; earlier defaults are replaced.
    """
    if ev.organisation_id:
        org = db.get(Organisation, ev.organisation_id)
        source_of = {r.code: r.source for r in organisation_codes(db, org)}
        basis = "organisation"
    else:
        source_of = {c: "sector_default" for c in default_codes_for_sector(db, ev.sector)}
        basis = "sector_default"

    existing = {r.code: r for r in db.execute(
        select(EvaluationGovernanceCode).where(EvaluationGovernanceCode.evaluation_id == ev.id)
    ).scalars().all()}
    for code, row in existing.items():
        if row.source == "sector_default" and code not in source_of:
            db.delete(row)
    for code, source in source_of.items():
        row = existing.get(code)
        if row is None:
            db.add(EvaluationGovernanceCode(evaluation_id=ev.id, code=code, source=source))
        elif row.source == "sector_default":
            row.source = source
    db.flush()
    rows = db.execute(
        select(EvaluationGovernanceCode).where(EvaluationGovernanceCode.evaluation_id == ev.id)
        .order_by(EvaluationGovernanceCode.code)
    ).scalars().all()
    return {"basis": basis, "codes": [{"code": r.code, "source": r.source} for r in rows]}


# ----------------------------
# Evaluations without an organisation (seed scripts, legacy rows)
# ----------------------------

def ensure_default_scope(db: Session, ev: Evaluation) -> None:
    """Put every active subject type in scope if the evaluation has no scope yet."""
    has_scope = db.execute(
        select(EvaluationScopeSubjectType).where(EvaluationScopeSubjectType.evaluation_id == ev.id).limit(1)
    ).first()
    if has_scope:
        return
    for code in db.execute(select(SubjectType.code).where(SubjectType.active == 1)).scalars().all():
        db.add(EvaluationScopeSubjectType(evaluation_id=ev.id, subject_type_code=code))


def ensure_organisation_for_evaluation(db: Session, ev: Evaluation) -> Organisation:
    """
    Same rules as the backfill migration: find the organisation by name
    (case-insensitive) or create it with the normalised sector and its default
    governance codes, then link and sync the evaluation and set default scope.
    Flushes but does not commit.
    """
    if ev.organisation_id:
        org = db.get(Organisation, ev.organisation_id)
    else:
        name = (ev.tenant_name or "").strip()
        org = db.execute(
            select(Organisation).where(func.lower(Organisation.name) == name.lower()).order_by(Organisation.created_at)
        ).scalars().first()
        if org is None:
            key, sub = normalize_sector(ev.sector)
            org = Organisation(name=name, sector_key=key, sector_sub_type=sub, country="NG")
            db.add(org)
            db.flush()
            link_sector_defaults(db, org)
    sync_evaluation_from_organisation(db, ev, org)
    db.flush()
    ensure_default_scope(db, ev)
    db.flush()
    return org

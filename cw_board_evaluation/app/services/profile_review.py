"""
app.services.profile_review
---------------------------
Consultant review of an organisation's profile (facts and committees), and
context snapshots for evaluations.

Rules:
- Manual entries are confirmed immediately (the consultant is the confirmer).
- Editing a proposal confirms it with the edited value.
- Confirming a proposal replaces the current confirmed value for that key.
- Any change to a confirmed fact or committee sets profile_status = draft.
- "Mark reviewed" needs no open proposals; it bumps profile_version.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BoardMember,
    CommitteeMembership,
    Evaluation,
    EvaluationContextSnapshot,
    EvaluationGovernanceCode,
    Organisation,
    OrganisationFact,
    OrgCommittee,
    OrgDocument,
)
from app.domain.org_profile import COMMITTEE_TYPES, FACT_SOURCES, FACTS_BY_KEY, validate_fact_value
from app.services.organisations import resync_organisation_evaluations


class ReviewError(ValueError):
    """A review action isn't allowed. The message is safe to show to users."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _profile_changed(db: Session, org: Organisation, key: Optional[str] = None) -> None:
    org.profile_status = "draft"
    if key == "regulator":
        db.flush()
        resync_organisation_evaluations(db, org)


def _check_source(source: str) -> str:
    if source not in FACT_SOURCES:
        raise ReviewError("Source must be public, client or consultant.")
    return source


# ----------------------------
# Facts
# ----------------------------
# One set of rules for every kind of profile fact (organisation and board
# member). A FactKind says which table, which owner column, how values are
# validated and what happens when the confirmed profile changes.

@dataclass(frozen=True)
class FactKind:
    model: Type
    owner_column: str                      # e.g. "organisation_id"
    validate: Callable[[str, Any], Any]
    on_change: Callable[[Session, Any, Optional[str]], None]  # (db, owner, key)


def _org_changed(db: Session, org: Organisation, key: Optional[str]) -> None:
    _profile_changed(db, org, key)


ORG_FACTS = FactKind(OrganisationFact, "organisation_id", validate_fact_value, _org_changed)


def _confirmed(db: Session, kind: FactKind, owner, key: str):
    col = getattr(kind.model, kind.owner_column)
    return db.execute(
        select(kind.model).where(col == owner.id, kind.model.key == key, kind.model.status == "confirmed")
    ).scalar_one_or_none()


def add_fact_of(db: Session, kind: FactKind, owner, *, key: str, value: Any, source: str, note: Optional[str] = None):
    """Manual entry: confirmed straight away (replacing any confirmed value for the key)."""
    value = kind.validate(key, value)
    _check_source(source)
    fact = _confirmed(db, kind, owner, key)
    if fact is None:
        fact = kind.model(key=key, **{kind.owner_column: owner.id})
        db.add(fact)
    fact.value, fact.source, fact.origin, fact.status = value, source, "manual", "confirmed"
    fact.source_document_id, fact.source_excerpt, fact.note = None, None, note
    fact.confirmed_at = _now()
    db.flush()
    kind.on_change(db, owner, key)
    db.flush()
    return fact


def confirm_fact_of(db: Session, kind: FactKind, owner, fact, *, value: Any = None,
                    source: Optional[str] = None, note: Optional[str] = None):
    """Confirm a proposal (optionally with an edited value). Replaces the current confirmed value."""
    if fact.status != "proposed":
        raise ReviewError("Only proposed facts can be confirmed.")
    new_value = kind.validate(fact.key, fact.value if value is None else value)
    edited = value is not None and new_value != fact.value
    current = _confirmed(db, kind, owner, fact.key)
    target = fact
    if current is not None:  # keep one confirmed row per key: move the proposal's provenance onto it
        target = current
        target.origin = fact.origin
        target.source_document_id, target.source_excerpt = fact.source_document_id, fact.source_excerpt
        db.delete(fact)
        db.flush()
    target.value = new_value
    target.source = _check_source(source) if source else fact.source
    target.note = note if note is not None else fact.note
    if edited:
        target.note = ((target.note + " ") if target.note else "") + "Edited by consultant before confirming."
    target.status, target.confirmed_at = "confirmed", _now()
    db.flush()
    kind.on_change(db, owner, target.key)
    db.flush()
    return target


def update_fact_of(db: Session, kind: FactKind, owner, fact, *, value: Any = None,
                   source: Optional[str] = None, note: Optional[str] = None):
    """Edit a fact. Editing a proposal confirms it; editing a confirmed fact sets the profile back to draft."""
    if fact.status == "proposed":
        return confirm_fact_of(db, kind, owner, fact, value=value, source=source, note=note)
    if fact.status != "confirmed":
        raise ReviewError("Rejected facts can't be edited; add the fact again instead.")
    if value is not None:
        fact.value = kind.validate(fact.key, value)
    if source is not None:
        fact.source = _check_source(source)
    if note is not None:
        fact.note = note
    fact.confirmed_at = _now()
    db.flush()
    kind.on_change(db, owner, fact.key)
    db.flush()
    return fact


def reject_fact_of(db: Session, kind: FactKind, owner, fact):
    if fact.status != "proposed":
        raise ReviewError("Only proposed facts can be rejected. Delete a confirmed fact instead.")
    fact.status = "rejected"
    db.flush()
    return fact


def delete_fact_of(db: Session, kind: FactKind, owner, fact) -> None:
    was_confirmed, key = fact.status == "confirmed", fact.key
    db.delete(fact)
    db.flush()
    if was_confirmed:
        kind.on_change(db, owner, key)
    db.flush()


# Organisation facts (unchanged signatures)

def add_fact(db: Session, org: Organisation, *, key: str, value: Any, source: str, note: Optional[str] = None) -> OrganisationFact:
    return add_fact_of(db, ORG_FACTS, org, key=key, value=value, source=source, note=note)


def confirm_fact(db: Session, org: Organisation, fact: OrganisationFact, *, value: Any = None,
                 source: Optional[str] = None, note: Optional[str] = None) -> OrganisationFact:
    return confirm_fact_of(db, ORG_FACTS, org, fact, value=value, source=source, note=note)


def update_fact(db: Session, org: Organisation, fact: OrganisationFact, *, value: Any = None,
                source: Optional[str] = None, note: Optional[str] = None) -> OrganisationFact:
    return update_fact_of(db, ORG_FACTS, org, fact, value=value, source=source, note=note)


def reject_fact(db: Session, org: Organisation, fact: OrganisationFact) -> OrganisationFact:
    return reject_fact_of(db, ORG_FACTS, org, fact)


def delete_fact(db: Session, org: Organisation, fact: OrganisationFact) -> None:
    delete_fact_of(db, ORG_FACTS, org, fact)


# ----------------------------
# Committees
# ----------------------------

def _clean_committee(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise ReviewError("Committee name is required.")
        out["name"] = name
    if "committee_type" in data:
        ctype = (data["committee_type"] or "other").strip().lower()
        if ctype not in COMMITTEE_TYPES:
            raise ReviewError(f"Committee type must be one of: {', '.join(COMMITTEE_TYPES)}.")
        out["committee_type"] = ctype
    if "chair_name" in data:
        out["chair_name"] = (data["chair_name"] or "").strip() or None
    if "member_names" in data:
        members = []
        for m in data["member_names"] or []:
            m = (str(m) or "").strip()
            if m and m not in members:
                members.append(m)
        out["member_names"] = members
    if "terms_of_reference_document_id" in data:
        out["terms_of_reference_document_id"] = data["terms_of_reference_document_id"]
    if "source" in data:
        out["source"] = _check_source(data["source"])
    return out


def add_committee(db: Session, org: Organisation, data: Dict[str, Any]) -> OrgCommittee:
    fields = _clean_committee({"committee_type": "other", "source": "consultant", **data})
    if "name" not in fields:
        raise ReviewError("Committee name is required.")
    c = OrgCommittee(organisation_id=org.id, status="confirmed", origin="manual", **fields)
    db.add(c)
    _profile_changed(db, org)
    db.flush()
    return c


def confirm_committee(db: Session, org: Organisation, c: OrgCommittee, data: Optional[Dict[str, Any]] = None) -> OrgCommittee:
    if c.status != "proposed":
        raise ReviewError("Only proposed committees can be confirmed.")
    for k, v in _clean_committee(data or {}).items():
        setattr(c, k, v)
    c.status = "confirmed"
    _profile_changed(db, org)
    db.flush()
    return c


def update_committee(db: Session, org: Organisation, c: OrgCommittee, data: Dict[str, Any]) -> OrgCommittee:
    """Edit a committee. Editing a proposal confirms it."""
    if c.status == "proposed":
        return confirm_committee(db, org, c, data)
    if c.status != "confirmed":
        raise ReviewError("Rejected committees can't be edited; add the committee again instead.")
    for k, v in _clean_committee(data).items():
        setattr(c, k, v)
    _profile_changed(db, org)
    db.flush()
    return c


def reject_committee(db: Session, org: Organisation, c: OrgCommittee) -> OrgCommittee:
    if c.status != "proposed":
        raise ReviewError("Only proposed committees can be rejected. Delete a confirmed committee instead.")
    c.status = "rejected"
    db.flush()
    return c


def delete_committee(db: Session, org: Organisation, c: OrgCommittee) -> None:
    was_confirmed = c.status == "confirmed"
    # Members confirmed on this committee lose it, so their profiles go back to draft
    linked = db.execute(
        select(BoardMember).join(CommitteeMembership, CommitteeMembership.board_member_id == BoardMember.id)
        .where(CommitteeMembership.committee_id == c.id, CommitteeMembership.status == "confirmed")
    ).scalars().all()
    for m in linked:
        m.profile_status = "draft"
    db.delete(c)
    if was_confirmed:
        _profile_changed(db, org)
    db.flush()


# ----------------------------
# Profile status
# ----------------------------

def open_proposals(db: Session, org: Organisation) -> Dict[str, int]:
    facts = db.execute(
        select(OrganisationFact).where(OrganisationFact.organisation_id == org.id, OrganisationFact.status == "proposed")
    ).scalars().all()
    committees = db.execute(
        select(OrgCommittee).where(OrgCommittee.organisation_id == org.id, OrgCommittee.status == "proposed")
    ).scalars().all()
    return {"facts": len(facts), "committees": len(committees)}


def mark_reviewed(db: Session, org: Organisation) -> Organisation:
    open_ = open_proposals(db, org)
    if open_["facts"] or open_["committees"]:
        raise ReviewError(
            f"Resolve the open proposals first ({open_['facts']} fact(s), {open_['committees']} committee(s))."
        )
    org.profile_status = "reviewed"
    org.profile_version = (org.profile_version or 1) + 1
    org.profile_reviewed_at = _now()
    db.flush()
    return org


# ----------------------------
# Context snapshots
# ----------------------------

def _fact_snapshot(f: OrganisationFact) -> Dict[str, Any]:
    return {
        "key": f.key,
        "label": FACTS_BY_KEY.get(f.key, {}).get("label", f.key),
        "value": f.value,
        "source": f.source,
        "origin": f.origin,
        "source_document_id": str(f.source_document_id) if f.source_document_id else None,
        "source_excerpt": f.source_excerpt,
        "note": f.note,
        "confirmed_at": f.confirmed_at.isoformat() if f.confirmed_at else None,
    }


def _committee_snapshot(c: OrgCommittee) -> Dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "committee_type": c.committee_type,
        "chair_name": c.chair_name,
        "member_names": list(c.member_names or []),
        "source": c.source,
        "terms_of_reference_document_id": str(c.terms_of_reference_document_id) if c.terms_of_reference_document_id else None,
    }


def snapshot_context(db: Session, evaluation_id: str) -> EvaluationContextSnapshot:
    """
    Freeze the organisation context an evaluation uses: confirmed facts and
    committees, the organisation's documents, the evaluation's governance
    codes, and each participant's board member profile (generation_only facts
    kept in their own key). Not called automatically yet (question assembly will call it).
    Flushes but does not commit.
    """
    ev = db.get(Evaluation, evaluation_id)
    if ev is None:
        raise LookupError(evaluation_id)
    org = db.get(Organisation, ev.organisation_id) if ev.organisation_id else None

    facts: List[Dict[str, Any]] = []
    committees: List[Dict[str, Any]] = []
    document_ids: List[str] = []
    if org is not None:
        facts = [_fact_snapshot(f) for f in db.execute(
            select(OrganisationFact).where(OrganisationFact.organisation_id == org.id, OrganisationFact.status == "confirmed")
            .order_by(OrganisationFact.key)
        ).scalars().all()]
        committees = [_committee_snapshot(c) for c in db.execute(
            select(OrgCommittee).where(OrgCommittee.organisation_id == org.id, OrgCommittee.status == "confirmed")
            .order_by(OrgCommittee.name)
        ).scalars().all()]
        document_ids = [str(d) for d in db.execute(
            select(OrgDocument.id).where(OrgDocument.organisation_id == org.id).order_by(OrgDocument.uploaded_at)
        ).scalars().all()]
    codes = [{"code": c.code, "source": c.source} for c in db.execute(
        select(EvaluationGovernanceCode).where(EvaluationGovernanceCode.evaluation_id == evaluation_id)
        .order_by(EvaluationGovernanceCode.code)
    ).scalars().all()]

    from app.services.board_members import participant_profiles  # board members build on this module

    people = participant_profiles(db, evaluation_id)
    snap = EvaluationContextSnapshot(
        evaluation_id=evaluation_id,
        profile_version=org.profile_version if org else 0,
        facts=facts,
        committees=committees,
        document_ids=document_ids,
        governance_codes=codes,
        participants=people["participants"],
        generation_only=people["generation_only"],
    )
    db.add(snap)
    db.flush()
    return snap

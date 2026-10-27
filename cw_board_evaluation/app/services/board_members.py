"""
app.services.board_members
--------------------------
Board members (organisation-level people), their profile review, committee
memberships, and keeping Participant.role in step with their confirmed role.

Fact review rules are the shared ones in app.services.profile_review
(FactKind); this module supplies the board member specifics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    BoardMember,
    BoardMemberFact,
    CommitteeMembership,
    Evaluation,
    Organisation,
    OrgCommittee,
    Participant,
)
from app.domain.board_member_profile import (
    GENERATION_ONLY_KEYS,
    PARTICIPANT_ROLE_FOR,
    PROFILE_FACTS_BY_KEY,
    all_independence_unknown,
    tenure_status,
    validate_profile_value,
)
from app.services.profile_review import (
    FactKind,
    ReviewError,
    _check_source,
    add_fact_of,
    confirm_fact_of,
    delete_fact_of,
    reject_fact_of,
    update_fact_of,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def member_label(m: BoardMember) -> str:
    """Name with the display code alongside, e.g. "P001 · Ada Obi"."""
    return f"{m.display_code} · {m.full_name}" if m.display_code else m.full_name


# ----------------------------
# Members
# ----------------------------

def _clean_email(email: Optional[str]) -> Optional[str]:
    e = (email or "").strip().lower()
    return e or None


def _clean_code(code: Optional[str]) -> Optional[str]:
    c = (code or "").strip().upper()
    return c or None


def _check_unique(db: Session, org_id, email: Optional[str], code: Optional[str], exclude_id=None) -> None:
    def clash(cond):
        stmt = select(BoardMember).where(BoardMember.organisation_id == org_id, cond)
        if exclude_id is not None:
            stmt = stmt.where(BoardMember.id != exclude_id)
        return db.execute(stmt).scalars().first()

    if email and clash(func.lower(BoardMember.email) == email):
        raise ReviewError(f"A board member with email {email} already exists for this company.")
    if code and clash(BoardMember.display_code == code):
        raise ReviewError(f"Display code {code} is already used for this company.")


def create_member(db: Session, org: Organisation, *, full_name: str, email: Optional[str] = None,
                  display_code: Optional[str] = None) -> BoardMember:
    name = (full_name or "").strip()
    if not name:
        raise ReviewError("Name is required.")
    email, code = _clean_email(email), _clean_code(display_code)
    _check_unique(db, org.id, email, code)
    m = BoardMember(organisation_id=org.id, full_name=name, email=email, display_code=code, active=True)
    db.add(m)
    db.flush()
    return m


def update_member(db: Session, m: BoardMember, data: Dict[str, Any]) -> BoardMember:
    if "full_name" in data:
        name = (data["full_name"] or "").strip()
        if not name:
            raise ReviewError("Name is required.")
        m.full_name = name
    email = _clean_email(data["email"]) if "email" in data else m.email
    code = _clean_code(data["display_code"]) if "display_code" in data else m.display_code
    _check_unique(db, m.organisation_id, email, code, exclude_id=m.id)
    m.email, m.display_code = email, code
    if "active" in data and data["active"] is not None:
        m.active = bool(data["active"])
    db.flush()
    return m


# ----------------------------
# Profile facts
# ----------------------------

def sync_participant_roles(db: Session, m: BoardMember) -> int:
    """
    Copy the confirmed governance_role onto the member's participants in DRAFT
    evaluations, using the Participant.role spelling the subject sync expects.
    Live and closed evaluations are left alone. Returns the number updated.
    """
    fact = db.execute(select(BoardMemberFact).where(
        BoardMemberFact.board_member_id == m.id,
        BoardMemberFact.key == "governance_role",
        BoardMemberFact.status == "confirmed",
    )).scalar_one_or_none()
    if fact is None:
        return 0
    role = PARTICIPANT_ROLE_FOR[fact.value]
    rows = db.execute(
        select(Participant).join(Evaluation, Evaluation.id == Participant.evaluation_id)
        .where(Participant.board_member_id == m.id, Evaluation.status == "draft")
    ).scalars().all()
    n = 0
    for p in rows:
        if p.role != role:
            p.role = role
            n += 1
    return n


def _member_changed(db: Session, m: BoardMember, key: Optional[str]) -> None:
    m.profile_status = "draft"
    if key == "governance_role":
        db.flush()
        sync_participant_roles(db, m)


MEMBER_FACTS = FactKind(BoardMemberFact, "board_member_id", validate_profile_value, _member_changed)


def add_member_fact(db, m, **kw):
    return add_fact_of(db, MEMBER_FACTS, m, **kw)


def confirm_member_fact(db, m, fact, **kw):
    return confirm_fact_of(db, MEMBER_FACTS, m, fact, **kw)


def update_member_fact(db, m, fact, **kw):
    return update_fact_of(db, MEMBER_FACTS, m, fact, **kw)


def reject_member_fact(db, m, fact):
    return reject_fact_of(db, MEMBER_FACTS, m, fact)


def delete_member_fact(db, m, fact):
    return delete_fact_of(db, MEMBER_FACTS, m, fact)


def confirmed_facts(db: Session, m: BoardMember) -> Dict[str, BoardMemberFact]:
    rows = db.execute(select(BoardMemberFact).where(
        BoardMemberFact.board_member_id == m.id, BoardMemberFact.status == "confirmed"
    )).scalars().all()
    return {f.key: f for f in rows}


def open_proposals(db: Session, m: BoardMember) -> Dict[str, int]:
    facts = db.execute(select(func.count()).select_from(BoardMemberFact).where(
        BoardMemberFact.board_member_id == m.id, BoardMemberFact.status == "proposed")).scalar_one()
    memberships = db.execute(select(func.count()).select_from(CommitteeMembership).where(
        CommitteeMembership.board_member_id == m.id, CommitteeMembership.status == "proposed")).scalar_one()
    return {"facts": facts, "memberships": memberships}


def review_blockers(db: Session, m: BoardMember) -> List[str]:
    """Why the profile can't be marked reviewed yet (empty list = it can)."""
    reasons = []
    if "governance_role" not in confirmed_facts(db, m):
        reasons.append("Confirm the governance role first.")
    o = open_proposals(db, m)
    if o["facts"] or o["memberships"]:
        reasons.append(f"Resolve the open proposals first ({o['facts']} fact(s), {o['memberships']} committee link(s)).")
    return reasons


def mark_member_reviewed(db: Session, m: BoardMember) -> BoardMember:
    reasons = review_blockers(db, m)
    if reasons:
        raise ReviewError(" ".join(reasons))
    m.profile_status = "reviewed"
    m.profile_version = (m.profile_version or 1) + 1
    m.profile_reviewed_at = _now()
    db.flush()
    return m


# ----------------------------
# Committee memberships
# ----------------------------

def _membership_member(db: Session, ms: CommitteeMembership) -> BoardMember:
    return db.get(BoardMember, ms.board_member_id)


def add_membership(db: Session, committee: OrgCommittee, m: BoardMember, *, membership_role: str = "member",
                   source: str = "consultant") -> CommitteeMembership:
    """Manual link: confirmed straight away."""
    if committee.organisation_id != m.organisation_id:
        raise ReviewError("The committee and the board member belong to different companies.")
    if membership_role not in ("member", "chair"):
        raise ReviewError("Role must be member or chair.")
    _check_source(source)
    ms = db.execute(select(CommitteeMembership).where(
        CommitteeMembership.committee_id == committee.id, CommitteeMembership.board_member_id == m.id
    )).scalar_one_or_none()
    if ms is None:
        ms = CommitteeMembership(committee_id=committee.id, board_member_id=m.id)
        db.add(ms)
    ms.membership_role, ms.source, ms.status, ms.origin = membership_role, source, "confirmed", "manual"
    m.profile_status = "draft"
    db.flush()
    return ms


def confirm_membership(db: Session, ms: CommitteeMembership, *, membership_role: Optional[str] = None) -> CommitteeMembership:
    if ms.status != "proposed":
        raise ReviewError("Only proposed committee links can be confirmed.")
    if membership_role is not None:
        if membership_role not in ("member", "chair"):
            raise ReviewError("Role must be member or chair.")
        ms.membership_role = membership_role
    ms.status = "confirmed"
    _membership_member(db, ms).profile_status = "draft"
    db.flush()
    return ms


def reject_membership(db: Session, ms: CommitteeMembership) -> CommitteeMembership:
    if ms.status != "proposed":
        raise ReviewError("Only proposed committee links can be rejected. Delete a confirmed link instead.")
    ms.status = "rejected"
    db.flush()
    return ms


def delete_membership(db: Session, ms: CommitteeMembership) -> None:
    member = _membership_member(db, ms)
    was_confirmed = ms.status == "confirmed"
    db.delete(ms)
    if was_confirmed and member is not None:
        member.profile_status = "draft"
    db.flush()


def member_committees(db: Session, m: BoardMember, statuses=("confirmed",)) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(CommitteeMembership, OrgCommittee)
        .join(OrgCommittee, OrgCommittee.id == CommitteeMembership.committee_id)
        .where(CommitteeMembership.board_member_id == m.id, CommitteeMembership.status.in_(statuses))
        .order_by(OrgCommittee.name)
    ).all()
    return [{
        "membership_id": str(ms.id),
        "committee_id": str(c.id),
        "committee_name": c.name,
        "committee_type": c.committee_type,
        "membership_role": ms.membership_role,
        "status": ms.status,
        "source": ms.source,
    } for ms, c in rows]


# ----------------------------
# Evaluation readiness and snapshots
# ----------------------------

READY, NEEDS_REVIEW, MISSING_ROLE, NOT_LINKED = "ready", "needs_review", "missing_role", "not_linked"


def participant_readiness(db: Session, ev: Evaluation) -> List[Dict[str, Any]]:
    """
    Per participant: readiness status, blocking reasons and warnings.
    Status (most severe first): not_linked, missing_role, needs_review, ready.
    An INED with every independence fact unknown is a warning, not a blocker.
    """
    out = []
    participants = db.execute(
        select(Participant).where(Participant.evaluation_id == ev.id).order_by(Participant.created_at)
    ).scalars().all()
    for p in participants:
        m = db.get(BoardMember, p.board_member_id) if p.board_member_id else None
        blocking: List[str] = []
        warnings: List[str] = []
        status = READY
        facts = confirmed_facts(db, m) if m else {}
        if m is None:
            status = NOT_LINKED
            blocking.append("Not linked to a board member.")
        else:
            role_fact = facts.get("governance_role")
            o = open_proposals(db, m)
            if role_fact is None:
                status = MISSING_ROLE
                blocking.append("No confirmed governance role.")
            if o["facts"] or o["memberships"]:
                blocking.append(f"{o['facts']} open fact proposal(s) and {o['memberships']} open committee link(s).")
            if m.profile_status != "reviewed":
                blocking.append("Profile not marked reviewed.")
            if status == READY and blocking:
                status = NEEDS_REVIEW
            if role_fact is not None and role_fact.value == "ined" and all_independence_unknown(
                {k: f.value for k, f in facts.items()}
            ):
                warnings.append("Independent NED with every independence question unknown.")
            if not m.active:
                warnings.append("Board member is marked inactive.")
        out.append({
            "participant_id": str(p.id),
            "full_name": p.full_name,
            "email": p.email,
            "board_member_id": str(m.id) if m else None,
            "display_code": m.display_code if m else None,
            "label": member_label(m) if m else (p.full_name or p.email),
            "governance_role": facts["governance_role"].value if "governance_role" in facts else None,
            "profile_status": m.profile_status if m else None,
            "profile_version": m.profile_version if m else None,
            "status": status,
            "blocking_reasons": blocking,
            "warnings": warnings,
        })
    return out


def _fact_dict(f: BoardMemberFact) -> Dict[str, Any]:
    return {
        "key": f.key,
        "label": PROFILE_FACTS_BY_KEY.get(f.key, {}).get("label", f.key),
        "value": f.value,
        "source": f.source,
        "origin": f.origin,
        "source_document_id": str(f.source_document_id) if f.source_document_id else None,
        "source_excerpt": f.source_excerpt,
        "confirmed_at": f.confirmed_at.isoformat() if f.confirmed_at else None,
    }


def participant_profiles(db: Session, evaluation_id: str) -> Dict[str, Any]:
    """
    Snapshot content for each participant's board member: profile version,
    confirmed facts and committee memberships. generation_only facts are
    returned separately (by participant id) so analysis never sees them.
    """
    participants: List[Dict[str, Any]] = []
    generation_only: Dict[str, List[Dict[str, Any]]] = {}
    rows = db.execute(
        select(Participant).where(Participant.evaluation_id == evaluation_id).order_by(Participant.created_at)
    ).scalars().all()
    for p in rows:
        m = db.get(BoardMember, p.board_member_id) if p.board_member_id else None
        entry: Dict[str, Any] = {
            "participant_id": str(p.id),
            "role": p.role,
            "board_member_id": str(m.id) if m else None,
            "display_code": m.display_code if m else None,
            "profile_version": m.profile_version if m else None,
            "profile_status": m.profile_status if m else None,
            "facts": [],
            "committee_memberships": [],
            "tenure": None,
        }
        if m is not None:
            facts = sorted(confirmed_facts(db, m).values(), key=lambda f: f.key)
            entry["facts"] = [_fact_dict(f) for f in facts if f.key not in GENERATION_ONLY_KEYS]
            hidden = [_fact_dict(f) for f in facts if f.key in GENERATION_ONLY_KEYS]
            if hidden:
                generation_only[str(p.id)] = hidden
            entry["committee_memberships"] = member_committees(db, m)
            appointment = next((f.value for f in facts if f.key == "board_appointment_date"), None)
            entry["tenure"] = tenure_status(appointment)
        participants.append(entry)
    return {"participants": participants, "generation_only": generation_only}

"""
app.api.board_members
---------------------
Board members of a company: profiles, documents, extraction, review and
committee memberships.

Endpoints (all under /api/v1, consultant auth):
- GET  /board-member-profile/registry
- GET/POST /organisations/{id}/board-members
- GET/PATCH /organisations/{id}/board-members/{member_id}
- POST /organisations/{id}/board-members/{member_id}/deactivate
- GET/POST /organisations/{id}/board-members/{member_id}/documents (multipart: file)
- GET  /organisations/{id}/board-members/{member_id}/documents/{doc_id}/download
- DELETE /organisations/{id}/board-members/{member_id}/documents/{doc_id}
- POST /organisations/{id}/board-members/{member_id}/extraction
- GET/POST /organisations/{id}/board-members/{member_id}/facts
- PATCH/DELETE /organisations/{id}/board-members/{member_id}/facts/{fact_id}
- POST /organisations/{id}/board-members/{member_id}/facts/{fact_id}/confirm | /reject
- POST /organisations/{id}/board-members/{member_id}/mark-reviewed
- GET/POST /organisations/{id}/committee-memberships
- POST /organisations/{id}/committee-memberships/match
- POST /organisations/{id}/committee-memberships/{membership_id}/confirm | /reject
- DELETE /organisations/{id}/committee-memberships/{membership_id}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.organisations import _child_or_404, _doc_dict, _org_or_404, _review_call, _uuid
from app.db.models import BoardMember, BoardMemberFact, CommitteeMembership, OrgCommittee, OrgDocument
from app.db.session import get_db
from app.domain.board_member_profile import (
    PROFILE_FACTS_BY_KEY,
    all_independence_unknown,
    effective_independence,
    registry_for_ui,
    tenure_status,
)
from app.services import board_members as svc
from app.services.committee_matching import match_committee_members
from app.services.member_extraction import run_member_extraction
from app.services.org_documents import delete_org_document, save_org_document
from app.services.org_extraction import ExtractionDisabled, ai_extraction_enabled
from app.services.storage import MAX_UPLOAD_BYTES, UploadRejected, get_storage

router = APIRouter()


# ----------------------------
# Helpers
# ----------------------------

def _member_or_404(db: Session, org, member_id: str) -> BoardMember:
    m = db.get(BoardMember, _uuid(member_id, "Board member"))
    if not m or m.organisation_id != org.id:
        raise HTTPException(status_code=404, detail="Board member not found.")
    return m


def _member_fact_or_404(db: Session, m: BoardMember, fact_id: str) -> BoardMemberFact:
    f = db.get(BoardMemberFact, _uuid(fact_id, "Fact"))
    if not f or f.board_member_id != m.id:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return f


def _membership_or_404(db: Session, org, membership_id: str) -> CommitteeMembership:
    ms = db.get(CommitteeMembership, _uuid(membership_id, "Committee link"))
    committee = db.get(OrgCommittee, ms.committee_id) if ms else None
    if not ms or committee is None or committee.organisation_id != org.id:
        raise HTTPException(status_code=404, detail="Committee link not found.")
    return ms


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _fact_dict(f: BoardMemberFact) -> Dict[str, Any]:
    spec = PROFILE_FACTS_BY_KEY.get(f.key, {})
    return {
        "fact_id": str(f.id),
        "key": f.key,
        "label": spec.get("label", f.key),
        "group": spec.get("group"),
        "generation_only": bool(spec.get("generation_only")),
        "value": f.value,
        "source": f.source,
        "status": f.status,
        "origin": f.origin,
        "source_document_id": str(f.source_document_id) if f.source_document_id else None,
        "source_excerpt": f.source_excerpt,
        "note": f.note,
        "created_at": _iso(f.created_at),
        "confirmed_at": _iso(f.confirmed_at),
    }


def _member_problems(db: Session, m: BoardMember, facts: Dict[str, BoardMemberFact]) -> List[str]:
    """Short list of things a consultant should look at (shown as a warning chip)."""
    problems = []
    if "governance_role" not in facts:
        problems.append("No confirmed role")
    o = svc.open_proposals(db, m)
    if o["facts"] or o["memberships"]:
        problems.append("Open proposals")
    role = facts.get("governance_role")
    if role is not None and role.value == "ined" and all_independence_unknown({k: f.value for k, f in facts.items()}):
        problems.append("Independence unknown")
    if not m.email:
        problems.append("No email")
    return problems


def _member_dict(db: Session, m: BoardMember, *, detail: bool = False) -> Dict[str, Any]:
    facts = svc.confirmed_facts(db, m)
    role = facts.get("governance_role")
    out = {
        "board_member_id": str(m.id),
        "full_name": m.full_name,
        "email": m.email,
        "display_code": m.display_code,
        "label": svc.member_label(m),
        "active": m.active,
        "governance_role": role.value if role else None,
        "profile_status": m.profile_status,
        "profile_version": m.profile_version,
        "profile_reviewed_at": _iso(m.profile_reviewed_at),
        "committees": svc.member_committees(db, m),
        "problems": _member_problems(db, m, facts),
        "created_at": _iso(m.created_at),
    }
    if detail:
        appointment = facts.get("board_appointment_date")
        out["tenure"] = tenure_status(appointment.value if appointment else None)
        out["independence"] = effective_independence({k: f.value for k, f in facts.items()})
        out["open_proposals"] = svc.open_proposals(db, m)
        out["review_blockers"] = svc.review_blockers(db, m)
        out["proposed_committees"] = svc.member_committees(db, m, statuses=("proposed",))
        out["ai_extraction_enabled"] = ai_extraction_enabled()
    return out


def _membership_dict(db: Session, ms: CommitteeMembership) -> Dict[str, Any]:
    c = db.get(OrgCommittee, ms.committee_id)
    m = db.get(BoardMember, ms.board_member_id)
    return {
        "membership_id": str(ms.id),
        "committee_id": str(c.id),
        "committee_name": c.name,
        "board_member_id": str(m.id),
        "board_member": svc.member_label(m),
        "membership_role": ms.membership_role,
        "source": ms.source,
        "status": ms.status,
        "origin": ms.origin,
        "matched_name": ms.matched_name,
        "created_at": _iso(ms.created_at),
    }


# ----------------------------
# Registry
# ----------------------------

@router.get("/board-member-profile/registry")
def get_member_registry() -> Dict[str, Any]:
    return {**registry_for_ui(), "ai_extraction_enabled": ai_extraction_enabled()}


# ----------------------------
# Board members
# ----------------------------

class MemberIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: Optional[str] = None
    display_code: Optional[str] = Field(default=None, max_length=32)


class MemberPatch(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = None
    display_code: Optional[str] = Field(default=None, max_length=32)
    active: Optional[bool] = None


@router.get("/organisations/{organisation_id}/board-members")
def list_members(organisation_id: str, include_inactive: bool = True, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    stmt = select(BoardMember).where(BoardMember.organisation_id == org.id)
    if not include_inactive:
        stmt = stmt.where(BoardMember.active.is_(True))
    rows = db.execute(stmt.order_by(BoardMember.active.desc(), func.lower(BoardMember.full_name))).scalars().all()
    return {"count": len(rows), "items": [_member_dict(db, m) for m in rows]}


@router.post("/organisations/{organisation_id}/board-members", status_code=201)
def create_member(organisation_id: str, payload: MemberIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _review_call(svc.create_member, db, org, full_name=payload.full_name, email=payload.email,
                     display_code=payload.display_code)
    db.commit()
    return _member_dict(db, m, detail=True)


@router.get("/organisations/{organisation_id}/board-members/{member_id}")
def get_member(organisation_id: str, member_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    return _member_dict(db, _member_or_404(db, org, member_id), detail=True)


@router.patch("/organisations/{organisation_id}/board-members/{member_id}")
def update_member(organisation_id: str, member_id: str, payload: MemberPatch, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    _review_call(svc.update_member, db, m, {k: getattr(payload, k) for k in payload.model_fields_set})
    db.commit()
    return _member_dict(db, m, detail=True)


@router.post("/organisations/{organisation_id}/board-members/{member_id}/deactivate")
def deactivate_member(organisation_id: str, member_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    svc.update_member(db, m, {"active": False})
    db.commit()
    return _member_dict(db, m, detail=True)


# ----------------------------
# Profile documents
# ----------------------------

def _member_doc_or_404(db: Session, org, m: BoardMember, doc_id: str) -> OrgDocument:
    doc = _child_or_404(db, OrgDocument, org, doc_id, "Document")
    if doc.board_member_id != m.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("/organisations/{organisation_id}/board-members/{member_id}/documents")
def list_member_documents(organisation_id: str, member_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    docs = db.execute(
        select(OrgDocument).where(OrgDocument.board_member_id == m.id).order_by(OrgDocument.uploaded_at)
    ).scalars().all()
    return {"count": len(docs), "items": [_doc_dict(d) for d in docs]}


@router.post("/organisations/{organisation_id}/board-members/{member_id}/documents", status_code=201)
async def upload_member_document(organisation_id: str, member_id: str, file: UploadFile = File(...),
                                 db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        doc = save_org_document(db, get_storage(), org, doc_type="director_profile", filename=file.filename or "",
                                data=data, board_member=m)
    except UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _doc_dict(doc)


@router.get("/organisations/{organisation_id}/board-members/{member_id}/documents/{document_id}/download")
def download_member_document(organisation_id: str, member_id: str, document_id: str,
                             db: Session = Depends(get_db)) -> Response:
    from app.api.organisations import download_document

    org = _org_or_404(db, organisation_id)
    _member_doc_or_404(db, org, _member_or_404(db, org, member_id), document_id)
    return download_document(organisation_id, document_id, db)


@router.delete("/organisations/{organisation_id}/board-members/{member_id}/documents/{document_id}")
def delete_member_document(organisation_id: str, member_id: str, document_id: str,
                           db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    doc = _member_doc_or_404(db, org, _member_or_404(db, org, member_id), document_id)
    delete_org_document(db, get_storage(), doc)
    db.commit()
    return {"deleted": True, "document_id": document_id}


@router.post("/organisations/{organisation_id}/board-members/{member_id}/extraction")
def run_member_profile_extraction(organisation_id: str, member_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    try:
        result = run_member_extraction(db, m)
    except ExtractionDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return result.as_dict()


# ----------------------------
# Facts
# ----------------------------

class MemberFactIn(BaseModel):
    key: str
    value: Any = None
    source: str
    note: Optional[str] = None


class MemberFactPatch(BaseModel):
    value: Any = None
    source: Optional[str] = None
    note: Optional[str] = None


@router.get("/organisations/{organisation_id}/board-members/{member_id}/facts")
def list_member_facts(organisation_id: str, member_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    rows = db.execute(
        select(BoardMemberFact).where(BoardMemberFact.board_member_id == m.id).order_by(BoardMemberFact.created_at)
    ).scalars().all()
    return {"count": len(rows), "items": [_fact_dict(f) for f in rows]}


@router.post("/organisations/{organisation_id}/board-members/{member_id}/facts", status_code=201)
def add_member_fact(organisation_id: str, member_id: str, payload: MemberFactIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    f = _review_call(svc.add_member_fact, db, m, key=payload.key, value=payload.value, source=payload.source,
                     note=payload.note)
    db.commit()
    return _fact_dict(f)


@router.patch("/organisations/{organisation_id}/board-members/{member_id}/facts/{fact_id}")
def update_member_fact(organisation_id: str, member_id: str, fact_id: str, payload: MemberFactPatch,
                       db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    f = _review_call(svc.update_member_fact, db, m, _member_fact_or_404(db, m, fact_id),
                     value=payload.value, source=payload.source, note=payload.note)
    db.commit()
    return _fact_dict(f)


@router.post("/organisations/{organisation_id}/board-members/{member_id}/facts/{fact_id}/confirm")
def confirm_member_fact(organisation_id: str, member_id: str, fact_id: str, payload: Optional[MemberFactPatch] = None,
                        db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    p = payload or MemberFactPatch()
    f = _review_call(svc.confirm_member_fact, db, m, _member_fact_or_404(db, m, fact_id),
                     value=p.value, source=p.source, note=p.note)
    db.commit()
    return _fact_dict(f)


@router.post("/organisations/{organisation_id}/board-members/{member_id}/facts/{fact_id}/reject")
def reject_member_fact(organisation_id: str, member_id: str, fact_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    f = _review_call(svc.reject_member_fact, db, m, _member_fact_or_404(db, m, fact_id))
    db.commit()
    return _fact_dict(f)


@router.delete("/organisations/{organisation_id}/board-members/{member_id}/facts/{fact_id}")
def delete_member_fact(organisation_id: str, member_id: str, fact_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    svc.delete_member_fact(db, m, _member_fact_or_404(db, m, fact_id))
    db.commit()
    return {"deleted": True, "fact_id": fact_id}


@router.post("/organisations/{organisation_id}/board-members/{member_id}/mark-reviewed")
def mark_member_reviewed(organisation_id: str, member_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    m = _member_or_404(db, org, member_id)
    try:
        svc.mark_member_reviewed(db, m)
    except svc.ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return _member_dict(db, m, detail=True)


# ----------------------------
# Committee memberships
# ----------------------------

class MembershipIn(BaseModel):
    committee_id: str
    board_member_id: str
    membership_role: str = "member"
    source: str = "consultant"


class MembershipConfirm(BaseModel):
    membership_role: Optional[str] = None


@router.get("/organisations/{organisation_id}/committee-memberships")
def list_memberships(organisation_id: str, status: Optional[str] = None, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    stmt = (select(CommitteeMembership)
            .join(OrgCommittee, OrgCommittee.id == CommitteeMembership.committee_id)
            .where(OrgCommittee.organisation_id == org.id))
    if status:
        stmt = stmt.where(CommitteeMembership.status == status)
    rows = db.execute(stmt.order_by(OrgCommittee.name, CommitteeMembership.created_at)).scalars().all()
    return {"count": len(rows), "items": [_membership_dict(db, ms) for ms in rows]}


@router.post("/organisations/{organisation_id}/committee-memberships/match")
def run_membership_matching(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    result = match_committee_members(db, org)
    db.commit()
    return result


@router.post("/organisations/{organisation_id}/committee-memberships", status_code=201)
def add_membership(organisation_id: str, payload: MembershipIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    committee = _child_or_404(db, OrgCommittee, org, payload.committee_id, "Committee")
    m = _member_or_404(db, org, payload.board_member_id)
    ms = _review_call(svc.add_membership, db, committee, m, membership_role=payload.membership_role,
                      source=payload.source)
    db.commit()
    return _membership_dict(db, ms)


@router.post("/organisations/{organisation_id}/committee-memberships/{membership_id}/confirm")
def confirm_membership(organisation_id: str, membership_id: str, payload: Optional[MembershipConfirm] = None,
                       db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    ms = _review_call(svc.confirm_membership, db, _membership_or_404(db, org, membership_id),
                      membership_role=(payload.membership_role if payload else None))
    db.commit()
    return _membership_dict(db, ms)


@router.post("/organisations/{organisation_id}/committee-memberships/{membership_id}/reject")
def reject_membership(organisation_id: str, membership_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    ms = _review_call(svc.reject_membership, db, _membership_or_404(db, org, membership_id))
    db.commit()
    return _membership_dict(db, ms)


@router.delete("/organisations/{organisation_id}/committee-memberships/{membership_id}")
def delete_membership(organisation_id: str, membership_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    svc.delete_membership(db, _membership_or_404(db, org, membership_id))
    db.commit()
    return {"deleted": True, "membership_id": membership_id}

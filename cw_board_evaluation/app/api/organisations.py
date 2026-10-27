"""
app.api.organisations
---------------------
Organisations (companies) and their profile: documents, facts, committees,
governance codes, AI extraction and review.

Endpoints (all under /api/v1, consultant auth):
- GET  /org-profile/registry
- GET  /organisations                     POST /organisations
- GET  /organisations/{id}                PATCH /organisations/{id}
- GET  /organisations/{id}/documents      POST /organisations/{id}/documents (multipart: doc_type, file)
- GET  /organisations/{id}/documents/{doc_id}/download
- DELETE /organisations/{id}/documents/{doc_id}
- POST /organisations/{id}/extraction
- GET/POST /organisations/{id}/facts      PATCH/DELETE /organisations/{id}/facts/{fact_id}
- POST /organisations/{id}/facts/{fact_id}/confirm | /reject
- GET/POST /organisations/{id}/committees PATCH/DELETE /organisations/{id}/committees/{committee_id}
- POST /organisations/{id}/committees/{committee_id}/confirm | /reject
- POST /organisations/{id}/mark-reviewed
- GET/PUT /organisations/{id}/governance-codes
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Evaluation,
    GovernanceCode,
    Organisation,
    OrganisationFact,
    OrgCommittee,
    OrgDocument,
)
from app.db.session import get_db
from app.domain.governance import SECTOR_KEYS, normalize_sector
from app.domain.org_profile import FACTS_BY_KEY, FactValueError, registry_for_ui
from app.services import profile_review as review
from app.services.org_documents import delete_org_document, save_org_document
from app.services.org_extraction import ExtractionDisabled, ai_extraction_enabled, run_extraction
from app.services.organisations import (
    UnknownGovernanceCode,
    link_sector_defaults,
    organisation_codes,
    resync_organisation_evaluations,
    set_organisation_codes,
)
from app.services.storage import MAX_UPLOAD_BYTES, UploadRejected, get_storage

router = APIRouter()


# ----------------------------
# Helpers
# ----------------------------

def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise HTTPException(status_code=404, detail=f"{what} not found.")


def _org_or_404(db: Session, organisation_id: str) -> Organisation:
    org = db.get(Organisation, _uuid(organisation_id, "Organisation"))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found.")
    return org


def _child_or_404(db: Session, model, org: Organisation, child_id: str, what: str):
    row = db.get(model, _uuid(child_id, what))
    if not row or row.organisation_id != org.id:
        raise HTTPException(status_code=404, detail=f"{what} not found.")
    return row


def _resolve_sector(sector_key: Optional[str], sector: Optional[str], sub_type: Optional[str]):
    """Accept either a sector key or free text (normalised). Returns (key, sub_type)."""
    key = (sector_key or "").strip().lower() or None
    sub = (sub_type or "").strip().lower() or None
    if key is None and (sector or "").strip():
        key, norm_sub = normalize_sector(sector)
        if key is None:
            raise HTTPException(
                status_code=400,
                detail=f"Sector '{sector}' isn't recognised. Use one of: {', '.join(SECTOR_KEYS)}.",
            )
        sub = sub or norm_sub
    if key is not None and key not in SECTOR_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown sector. Use one of: {', '.join(SECTOR_KEYS)}.")
    return key, sub


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _latest_evaluation(db: Session, org_id) -> Optional[Dict[str, Any]]:
    ev = db.execute(
        select(Evaluation).where(Evaluation.organisation_id == org_id).order_by(Evaluation.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if not ev:
        return None
    return {"evaluation_id": ev.id, "name": ev.name, "year": ev.year, "status": ev.status, "created_at": _iso(ev.created_at)}


def _org_dict(db: Session, org: Organisation, *, detail: bool = False) -> Dict[str, Any]:
    out = {
        "organisation_id": str(org.id),
        "name": org.name,
        "sector_key": org.sector_key,
        "sector_sub_type": org.sector_sub_type,
        "country": org.country,
        "profile_status": org.profile_status,
        "profile_version": org.profile_version,
        "profile_reviewed_at": _iso(org.profile_reviewed_at),
        "created_at": _iso(org.created_at),
        "updated_at": _iso(org.updated_at),
        "latest_evaluation": _latest_evaluation(db, org.id),
    }
    if detail:
        out["open_proposals"] = review.open_proposals(db, org)
        out["evaluation_count"] = db.execute(
            select(func.count()).select_from(Evaluation).where(Evaluation.organisation_id == org.id)
        ).scalar_one()
        out["ai_extraction_enabled"] = ai_extraction_enabled()
    return out


def _doc_dict(d: OrgDocument) -> Dict[str, Any]:
    return {
        "document_id": str(d.id),
        "doc_type": d.doc_type,
        "filename": d.filename,
        "content_type": d.content_type,
        "size_bytes": d.size_bytes,
        "extraction_status": d.extraction_status,
        "extraction_error": d.extraction_error,
        "text_chars": len(d.extracted_text or ""),
        "uploaded_at": _iso(d.uploaded_at),
    }


def _fact_dict(f: OrganisationFact) -> Dict[str, Any]:
    spec = FACTS_BY_KEY.get(f.key, {})
    return {
        "fact_id": str(f.id),
        "key": f.key,
        "label": spec.get("label", f.key),
        "group": spec.get("group"),
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


def _committee_dict(c: OrgCommittee) -> Dict[str, Any]:
    return {
        "committee_id": str(c.id),
        "name": c.name,
        "committee_type": c.committee_type,
        "chair_name": c.chair_name,
        "member_names": list(c.member_names or []),
        "terms_of_reference_document_id": str(c.terms_of_reference_document_id) if c.terms_of_reference_document_id else None,
        "source": c.source,
        "status": c.status,
        "origin": c.origin,
        "source_document_id": str(c.source_document_id) if c.source_document_id else None,
        "source_excerpt": c.source_excerpt,
        "created_at": _iso(c.created_at),
    }


def _review_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (review.ReviewError, FactValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ----------------------------
# Registry
# ----------------------------

@router.get("/org-profile/registry")
def get_profile_registry() -> Dict[str, Any]:
    """Fact keys, groups, sources, document and committee types, for rendering forms."""
    return {**registry_for_ui(), "sector_keys": SECTOR_KEYS, "ai_extraction_enabled": ai_extraction_enabled()}


# ----------------------------
# Organisations
# ----------------------------

class OrganisationIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sector_key: Optional[str] = None
    sector: Optional[str] = None  # free text, normalised (alternative to sector_key)
    sector_sub_type: Optional[str] = None
    country: str = "NG"


class OrganisationPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sector_key: Optional[str] = None
    sector: Optional[str] = None
    sector_sub_type: Optional[str] = None
    country: Optional[str] = None


@router.get("/organisations")
def list_organisations(db: Session = Depends(get_db)) -> Dict[str, Any]:
    orgs = db.execute(select(Organisation).order_by(func.lower(Organisation.name))).scalars().all()
    items = [_org_dict(db, o) for o in orgs]
    return {"count": len(items), "items": items}


@router.post("/organisations", status_code=201)
def create_organisation(payload: OrganisationIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required.")
    dup = db.execute(select(Organisation).where(func.lower(Organisation.name) == name.lower())).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"A company called '{dup.name}' already exists.")
    key, sub = _resolve_sector(payload.sector_key, payload.sector, payload.sector_sub_type)
    org = Organisation(name=name, sector_key=key, sector_sub_type=sub, country=(payload.country or "NG").strip().upper()[:8])
    db.add(org)
    db.flush()
    link_sector_defaults(db, org)
    db.commit()
    db.refresh(org)
    return _org_dict(db, org, detail=True)


@router.get("/organisations/{organisation_id}")
def get_organisation(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _org_dict(db, _org_or_404(db, organisation_id), detail=True)


@router.patch("/organisations/{organisation_id}")
def update_organisation(organisation_id: str, payload: OrganisationPatch, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    sent = payload.model_fields_set
    if payload.name is not None:
        name = payload.name.strip()
        dup = db.execute(
            select(Organisation).where(func.lower(Organisation.name) == name.lower(), Organisation.id != org.id)
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail=f"A company called '{dup.name}' already exists.")
        org.name = name
    if {"sector_key", "sector", "sector_sub_type"} & sent:
        if {"sector_key", "sector"} & sent:  # a new sector (key or free text); sub-type as sent
            key, sub = _resolve_sector(payload.sector_key, payload.sector, payload.sector_sub_type)
        else:  # only the sub-type changes
            key, sub = org.sector_key, (payload.sector_sub_type or "").strip().lower() or None
        changed = (key, sub) != (org.sector_key, org.sector_sub_type)
        org.sector_key, org.sector_sub_type = key, sub
        if changed:
            db.flush()
            link_sector_defaults(db, org)
    if payload.country is not None:
        org.country = payload.country.strip().upper()[:8] or "NG"
    db.flush()
    resync_organisation_evaluations(db, org)
    db.commit()
    db.refresh(org)
    return _org_dict(db, org, detail=True)


# ----------------------------
# Documents
# ----------------------------

@router.get("/organisations/{organisation_id}/documents")
def list_documents(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    docs = db.execute(
        select(OrgDocument)
        .where(OrgDocument.organisation_id == org.id, OrgDocument.board_member_id.is_(None))
        .order_by(OrgDocument.uploaded_at)
    ).scalars().all()
    return {"count": len(docs), "items": [_doc_dict(d) for d in docs]}


@router.post("/organisations/{organisation_id}/documents", status_code=201)
async def upload_document(
    organisation_id: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)  # never read more than the limit + 1 byte
    try:
        doc = save_org_document(db, get_storage(), org, doc_type=doc_type, filename=file.filename or "", data=data)
    except UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _doc_dict(doc)


@router.get("/organisations/{organisation_id}/documents/{document_id}/download")
def download_document(organisation_id: str, document_id: str, db: Session = Depends(get_db)) -> Response:
    org = _org_or_404(db, organisation_id)
    doc = _child_or_404(db, OrgDocument, org, document_id, "Document")
    try:
        data = get_storage().read(doc.storage_key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="The stored file is missing.")
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.filename)}"},
    )


@router.delete("/organisations/{organisation_id}/documents/{document_id}")
def delete_document(organisation_id: str, document_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    doc = _child_or_404(db, OrgDocument, org, document_id, "Document")
    delete_org_document(db, get_storage(), doc)
    db.commit()
    return {"deleted": True, "document_id": document_id}


# ----------------------------
# AI extraction
# ----------------------------

@router.post("/organisations/{organisation_id}/extraction")
def run_profile_extraction(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    try:
        result = run_extraction(db, org)
    except ExtractionDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return result.as_dict()


# ----------------------------
# Facts
# ----------------------------

class FactIn(BaseModel):
    key: str
    value: Any = None
    source: str
    note: Optional[str] = None


class FactPatch(BaseModel):
    value: Any = None
    source: Optional[str] = None
    note: Optional[str] = None


@router.get("/organisations/{organisation_id}/facts")
def list_facts(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    facts = db.execute(
        select(OrganisationFact).where(OrganisationFact.organisation_id == org.id).order_by(OrganisationFact.created_at)
    ).scalars().all()
    return {"count": len(facts), "items": [_fact_dict(f) for f in facts]}


@router.post("/organisations/{organisation_id}/facts", status_code=201)
def add_fact(organisation_id: str, payload: FactIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    fact = _review_call(review.add_fact, db, org, key=payload.key, value=payload.value, source=payload.source, note=payload.note)
    db.commit()
    return _fact_dict(fact)


@router.patch("/organisations/{organisation_id}/facts/{fact_id}")
def update_fact(organisation_id: str, fact_id: str, payload: FactPatch, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    fact = _child_or_404(db, OrganisationFact, org, fact_id, "Fact")
    fact = _review_call(review.update_fact, db, org, fact, value=payload.value, source=payload.source, note=payload.note)
    db.commit()
    return _fact_dict(fact)


@router.post("/organisations/{organisation_id}/facts/{fact_id}/confirm")
def confirm_fact(organisation_id: str, fact_id: str, payload: Optional[FactPatch] = None,
                 db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    fact = _child_or_404(db, OrganisationFact, org, fact_id, "Fact")
    p = payload or FactPatch()
    fact = _review_call(review.confirm_fact, db, org, fact, value=p.value, source=p.source, note=p.note)
    db.commit()
    return _fact_dict(fact)


@router.post("/organisations/{organisation_id}/facts/{fact_id}/reject")
def reject_fact(organisation_id: str, fact_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    fact = _child_or_404(db, OrganisationFact, org, fact_id, "Fact")
    fact = _review_call(review.reject_fact, db, org, fact)
    db.commit()
    return _fact_dict(fact)


@router.delete("/organisations/{organisation_id}/facts/{fact_id}")
def delete_fact(organisation_id: str, fact_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    fact = _child_or_404(db, OrganisationFact, org, fact_id, "Fact")
    review.delete_fact(db, org, fact)
    db.commit()
    return {"deleted": True, "fact_id": fact_id}


# ----------------------------
# Committees
# ----------------------------

class CommitteeIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    committee_type: str = "other"
    chair_name: Optional[str] = None
    member_names: List[str] = Field(default_factory=list)
    terms_of_reference_document_id: Optional[str] = None
    source: str = "consultant"


class CommitteePatch(BaseModel):
    name: Optional[str] = None
    committee_type: Optional[str] = None
    chair_name: Optional[str] = None
    member_names: Optional[List[str]] = None
    terms_of_reference_document_id: Optional[str] = None
    source: Optional[str] = None


def _committee_data(db: Session, org: Organisation, payload: BaseModel) -> Dict[str, Any]:
    data = {k: getattr(payload, k) for k in payload.model_fields_set}
    tor = data.get("terms_of_reference_document_id")
    if tor:
        data["terms_of_reference_document_id"] = _child_or_404(db, OrgDocument, org, tor, "Document").id
    return data


@router.get("/organisations/{organisation_id}/committees")
def list_committees(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    rows = db.execute(
        select(OrgCommittee).where(OrgCommittee.organisation_id == org.id).order_by(OrgCommittee.created_at)
    ).scalars().all()
    return {"count": len(rows), "items": [_committee_dict(c) for c in rows]}


@router.post("/organisations/{organisation_id}/committees", status_code=201)
def add_committee(organisation_id: str, payload: CommitteeIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    data = _committee_data(db, org, payload)
    data.setdefault("name", payload.name)
    c = _review_call(review.add_committee, db, org, data)
    db.commit()
    return _committee_dict(c)


@router.patch("/organisations/{organisation_id}/committees/{committee_id}")
def update_committee(organisation_id: str, committee_id: str, payload: CommitteePatch,
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    c = _child_or_404(db, OrgCommittee, org, committee_id, "Committee")
    c = _review_call(review.update_committee, db, org, c, _committee_data(db, org, payload))
    db.commit()
    return _committee_dict(c)


@router.post("/organisations/{organisation_id}/committees/{committee_id}/confirm")
def confirm_committee(organisation_id: str, committee_id: str, payload: Optional[CommitteePatch] = None,
                      db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    c = _child_or_404(db, OrgCommittee, org, committee_id, "Committee")
    c = _review_call(review.confirm_committee, db, org, c, _committee_data(db, org, payload or CommitteePatch()))
    db.commit()
    return _committee_dict(c)


@router.post("/organisations/{organisation_id}/committees/{committee_id}/reject")
def reject_committee(organisation_id: str, committee_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    c = _child_or_404(db, OrgCommittee, org, committee_id, "Committee")
    c = _review_call(review.reject_committee, db, org, c)
    db.commit()
    return _committee_dict(c)


@router.delete("/organisations/{organisation_id}/committees/{committee_id}")
def delete_committee(organisation_id: str, committee_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    c = _child_or_404(db, OrgCommittee, org, committee_id, "Committee")
    review.delete_committee(db, org, c)
    db.commit()
    return {"deleted": True, "committee_id": committee_id}


# ----------------------------
# Review
# ----------------------------

@router.post("/organisations/{organisation_id}/mark-reviewed")
def mark_reviewed(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    try:
        review.mark_reviewed(db, org)
    except review.ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    db.refresh(org)
    return _org_dict(db, org, detail=True)


# ----------------------------
# Governance codes
# ----------------------------

class OrgCodesIn(BaseModel):
    codes: List[str] = Field(default_factory=list)


def _codes_response(db: Session, org: Organisation) -> Dict[str, Any]:
    rows = organisation_codes(db, org)
    meta = {g.code: g for g in db.execute(
        select(GovernanceCode).where(GovernanceCode.code.in_([r.code for r in rows]))
    ).scalars().all()}
    items = [{
        "code": r.code,
        "source": r.source,
        "title": meta[r.code].title,
        "issuer": meta[r.code].issuer,
        "status": meta[r.code].status,
        "clauses_loaded": bool(meta[r.code].clauses_loaded),
    } for r in rows]
    return {"organisation_id": str(org.id), "count": len(items), "items": items}


@router.get("/organisations/{organisation_id}/governance-codes")
def get_org_codes(organisation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _codes_response(db, _org_or_404(db, organisation_id))


@router.put("/organisations/{organisation_id}/governance-codes")
def put_org_codes(organisation_id: str, payload: OrgCodesIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    org = _org_or_404(db, organisation_id)
    try:
        set_organisation_codes(db, org, payload.codes)
    except UnknownGovernanceCode as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _codes_response(db, org)

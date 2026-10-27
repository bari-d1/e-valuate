"""
app.services.org_documents
--------------------------
Upload, text extraction and deletion of organisation documents.
Document contents are never logged.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import BoardMember, Organisation, OrgDocument
from app.domain.org_profile import DOC_TYPE_KEYS
from app.services.document_text import DocumentTextError, extract_document_text
from app.services.storage import Storage, UploadRejected, sanitize_filename, validate_upload

log = logging.getLogger(__name__)


def save_org_document(
    db: Session,
    storage: Storage,
    org: Organisation,
    *,
    doc_type: str,
    filename: str,
    data: bytes,
    board_member: Optional[BoardMember] = None,
) -> OrgDocument:
    """
    Validate, store and extract text from an uploaded document.
    Raises UploadRejected for bad type/size. Text extraction failures don't
    reject the upload: the document is kept with extraction_status = failed.
    Flushes but does not commit.
    """
    if board_member is not None:
        # A board member's own documents (CV, director profile)
        if doc_type != "director_profile" or board_member.organisation_id != org.id:
            raise UploadRejected("Board member documents must be director profiles for that member's company.")
    elif doc_type not in DOC_TYPE_KEYS:
        raise UploadRejected(f"Unknown document type: {doc_type}")
    ext, content_type = validate_upload(filename, data)
    key = storage.save(data, ext)

    doc = OrgDocument(
        organisation_id=org.id,
        board_member_id=board_member.id if board_member is not None else None,
        doc_type=doc_type,
        filename=sanitize_filename(filename, ext),
        content_type=content_type,
        size_bytes=len(data),
        storage_key=key,
        extraction_status="pending",
    )
    try:
        doc.extracted_text = extract_document_text(doc.filename, data)
        doc.extraction_status = "done"
    except DocumentTextError as exc:
        doc.extraction_status = "failed"
        doc.extraction_error = str(exc)
        log.info("Text extraction failed for document %s (%s): %s", key, doc_type, exc)

    db.add(doc)
    try:
        db.flush()
    except Exception:
        storage.delete(key)  # don't leave an orphaned file behind
        raise
    return doc


def delete_org_document(db: Session, storage: Storage, doc: OrgDocument) -> None:
    """Delete the stored file and the document row. Flushes but does not commit."""
    key = doc.storage_key
    db.delete(doc)
    db.flush()
    storage.delete(key)

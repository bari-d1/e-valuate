"""
Extract plain text from uploaded documents for AI questionnaire generation.
"""

from __future__ import annotations

import io

from fastapi import HTTPException


def _normalize_filename(filename: str) -> str:
    return (filename or "").strip().lower()


def extract_docx_text(raw: bytes) -> str:
    """Pull paragraph and table cell text from a .docx file."""
    from docx import Document

    doc = Document(io.BytesIO(raw))
    parts: list[str] = []

    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if text:
            parts.append(text)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = (cell.text or "").strip()
                if text:
                    parts.append(text)

    return "\n".join(parts).strip()


def extract_text_from_upload(filename: str, raw: bytes) -> str:
    """
    Return UTF-8 plain text from supported upload types.

    Supported: .txt, .md, .markdown, .docx
    """
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    name = _normalize_filename(filename)

    if name.endswith((".txt", ".md", ".markdown")):
        return raw.decode("utf-8", errors="ignore").strip()

    if name.endswith(".docx"):
        try:
            text = extract_docx_text(raw)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read DOCX file: {exc}",
            ) from exc
        if not text:
            raise HTTPException(
                status_code=400,
                detail="DOCX file contained no extractable text (empty document).",
            )
        return text

    if name.endswith(".doc"):
        raise HTTPException(
            status_code=400,
            detail="Legacy .doc files are not supported. Save as .docx or export to .txt and upload again.",
        )

    if name.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="PDF extraction is not supported yet. Save as .docx or .txt and upload again.",
        )

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Upload .txt, .md, or .docx.",
    )

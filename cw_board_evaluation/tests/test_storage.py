"""
Unit tests for document storage rules and text extraction (no database).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.document_text import DocumentTextError, extract_document_text
from app.services.storage import (
    MAX_UPLOAD_BYTES,
    LocalDiskStorage,
    UploadRejected,
    sanitize_filename,
    validate_upload,
)


def _pdf_with_text(text: str) -> bytes:
    """A minimal valid one-page PDF with a text layer."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _docx_with_text(text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# ----------------------------
# Type and size limits
# ----------------------------

def test_accepts_pdf_docx_txt() -> None:
    assert validate_upload("a.pdf", _pdf_with_text("x"))[1] == "application/pdf"
    assert validate_upload("a.DOCX", _docx_with_text("x"))[0] == ".docx"
    assert validate_upload("a.txt", b"hello")[1] == "text/plain"


@pytest.mark.parametrize(
    "name,data,message",
    [
        ("a.exe", b"MZ", "Only PDF"),
        ("a.doc", b"x", "Only PDF"),
        ("noext", b"x", "Only PDF"),
        ("a.pdf", b"not a pdf", "valid PDF"),
        ("a.docx", b"PK not a zip", "valid Word"),
        ("a.txt", b"", "empty"),
        ("a.txt", "caf\u00e9".encode("latin-1"), "UTF-8"),
    ],
)
def test_rejects_bad_types(name, data, message) -> None:
    with pytest.raises(UploadRejected, match=message):
        validate_upload(name, data)


def test_rejects_zip_that_is_not_docx() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(UploadRejected, match="valid Word"):
        validate_upload("a.docx", buf.getvalue())


def test_size_limit() -> None:
    assert MAX_UPLOAD_BYTES == 25 * 1024 * 1024
    ok = b"%PDF-" + b"0" * (MAX_UPLOAD_BYTES - 5)
    assert validate_upload("big.pdf", ok)[0] == ".pdf"
    with pytest.raises(UploadRejected, match="25 MB"):
        validate_upload("big.pdf", ok + b"0")


# ----------------------------
# Filenames and keys
# ----------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Annual Report 2024.pdf", "Annual Report 2024.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\x\\Board Charter.pdf", "Board Charter.pdf"),
        ("evil\x00name<script>.pdf", "evilname_script.pdf"),
        ("....pdf", "document.pdf"),
        ("report.PDF", "report.pdf"),
    ],
)
def test_sanitize_filename(raw, expected) -> None:
    assert sanitize_filename(raw, ".pdf") == expected


def test_sanitize_filename_length() -> None:
    assert len(sanitize_filename("x" * 500 + ".txt", ".txt")) <= 120


def test_storage_save_read_delete(tmp_path) -> None:
    st = LocalDiskStorage(tmp_path)
    key = st.save(b"hello", ".txt")
    assert key.startswith("org-docs/") and key.endswith(".txt")
    assert st.exists(key) and st.read(key) == b"hello"
    st.delete(key)
    assert not st.exists(key)
    assert not (tmp_path / key).exists()
    st.delete(key)  # deleting twice is fine


@pytest.mark.parametrize("key", ["../../etc/passwd", "org-docs/../../x.txt", "/abs/path.txt", "org-docs/NOTHEX.txt"])
def test_storage_rejects_user_paths(tmp_path, key) -> None:
    with pytest.raises(ValueError):
        LocalDiskStorage(tmp_path).read(key)


def test_storage_keys_are_generated(tmp_path) -> None:
    st = LocalDiskStorage(tmp_path)
    assert st.save(b"a", ".pdf") != st.save(b"a", ".pdf")


# ----------------------------
# Text extraction
# ----------------------------

def test_extract_text_from_each_type() -> None:
    assert "nine directors" in extract_document_text("a.pdf", _pdf_with_text("The Board has nine directors."))
    assert extract_document_text("a.docx", _docx_with_text("Audit Committee")) == "Audit Committee"
    assert extract_document_text("a.txt", b"  plain text  ") == "plain text"


def test_extract_text_failures() -> None:
    with pytest.raises(DocumentTextError, match="No text"):
        extract_document_text("a.pdf", _pdf_with_text(""))
    with pytest.raises(DocumentTextError):
        extract_document_text("a.pdf", b"%PDF-garbage")

"""
app.services.storage
--------------------
File storage for uploaded organisation documents.

`Storage` is the interface; `LocalDiskStorage` stores files under STORAGE_DIR
(default: cw_board_evaluation/storage). A cloud implementation can replace it
by returning a different object from get_storage().

Rules:
- Only PDF, DOCX and TXT, max 25 MB, checked by content, not just extension.
- Files are stored under generated keys; user input never becomes a path.
- Document contents are never logged.
"""

from __future__ import annotations

import os
import re
import unicodedata
import uuid
import zipfile
import io
from pathlib import Path
from typing import Protocol

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# extension -> stored content type
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}

_KEY_RE = re.compile(r"^org-docs/[0-9a-f]{32}\.(pdf|docx|txt)$")


class UploadRejected(ValueError):
    """The upload breaks a type or size rule. The message is safe to show to users."""


class Storage(Protocol):
    def save(self, data: bytes, extension: str) -> str: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


def sanitize_filename(name: str, extension: str) -> str:
    """
    A display-safe filename: no directories, control characters or odd
    punctuation, at most 120 characters, ending in the validated extension.
    Only used for display and downloads, never as a storage path.
    """
    base = re.split(r"[\\/]", name or "")[-1]
    base = unicodedata.normalize("NFKC", base)
    stem = base[: -len(extension)] if base.lower().endswith(extension) else os.path.splitext(base)[0]
    stem = "".join(ch for ch in stem if ch.isprintable())
    stem = re.sub(r"[^A-Za-z0-9 ._()&,-]+", "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._")
    stem = stem[: 120 - len(extension)] or "document"
    return f"{stem}{extension}"


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    """
    Check type and size. Returns (extension, content_type) or raises UploadRejected.
    The type is decided by extension AND content; the client's content type is ignored.
    """
    ext = os.path.splitext((filename or "").strip().lower())[1]
    if ext not in ALLOWED_TYPES:
        raise UploadRejected("Only PDF, Word (.docx) and plain text (.txt) files can be uploaded.")
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("The file is larger than 25 MB.")

    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise UploadRejected("The file isn't a valid PDF.")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" not in z.namelist():
                    raise UploadRejected("The file isn't a valid Word (.docx) document.")
        except zipfile.BadZipFile:
            raise UploadRejected("The file isn't a valid Word (.docx) document.")
    if ext == ".txt":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadRejected("Text files must be UTF-8 encoded.")
    return ext, ALLOWED_TYPES[ext]


class LocalDiskStorage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key or ""):
            raise ValueError("Invalid storage key.")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key.")
        return path

    def save(self, data: bytes, extension: str) -> str:
        if extension not in ALLOWED_TYPES:
            raise ValueError("Unsupported extension.")
        key = f"org-docs/{uuid.uuid4().hex}{extension}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def default_storage_dir() -> Path:
    configured = (os.getenv("STORAGE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "storage"


def get_storage() -> Storage:
    return LocalDiskStorage(default_storage_dir())

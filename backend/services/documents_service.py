"""Documents block: DSS Managed Folder (bytes) + SQLite metadata.

The managed folder is resolved by name (not a hardcoded ID) so the block is
portable across projects.  Resolution order:
  1. ``documents_folder_id`` stored in the app-settings project variable.
  2. Lookup a folder named ``f"{PREFIX} Documents"`` in the project; cache its id.
  3. Create the folder; cache its id.
  4. Raise a clear 503 if creation fails (e.g. no writable connection locally).

``get_project()`` returns a dataikuapi DSSProject in both local dev and
in-DSS modes (the dual-mode accessor in dss_client.py), so
``create_managed_folder()``, ``list_managed_folders()``, and folder
file I/O are single-path code.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from threading import RLock
from typing import Literal

from .db import get_conn
from ..config import PREFIX
from ..dss_client import get_project

# ── Allowed upload types ───────────────────────────────────────────────────────

ALLOWED_EXT = {
    ".pdf",
    ".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif",
    ".mp3", ".wav", ".flac", ".ogg", ".aac",
    ".mp4", ".mov", ".webm",
    ".txt", ".md", ".html", ".htm", ".py",
    ".json", ".csv", ".xml", ".rtf",
}

_MIME_FROM_EXT: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
    ".ogg": "audio/ogg", ".aac": "audio/aac",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".txt": "text/plain", ".md": "text/markdown", ".html": "text/html",
    ".htm": "text/html", ".py": "text/x-python", ".json": "application/json",
    ".csv": "text/csv", ".xml": "text/xml", ".rtf": "text/rtf",
}

_TEXT_MIME_PREFIXES = ("text/",)
_TEXT_MIME_EXACT = frozenset({"application/json"})
MAX_TEXT_CHARS = 200_000

_lock = RLock()

# ── Managed folder helpers ─────────────────────────────────────────────────────

_FOLDER_NAME = f"{PREFIX} Documents"
_cached_folder_id: str | None = None


def _resolve_folder_id() -> str:
    """Resolve the DSS managed folder id by name, creating it if needed.

    Caches the id in the app-settings project variable (``documents_folder_id``)
    so the list scan only happens once per deployment.
    """
    global _cached_folder_id
    if _cached_folder_id is not None:
        return _cached_folder_id

    from . import settings as settings_service  # noqa: PLC0415

    saved: str | None = settings_service.get_settings().get("documents_folder_id")
    if saved:
        _cached_folder_id = saved
        return saved

    project = get_project()
    found_id: str | None = None

    for mf in project.list_managed_folders():
        info: dict = mf if isinstance(mf, dict) else getattr(mf, "_data", {})
        if info.get("name") == _FOLDER_NAME:
            fid: str | None = info.get("id") or info.get("folderBasicInfo", {}).get("id")
            if fid:
                found_id = fid
                break

    if found_id is None:
        # Folder does not exist — create it.
        try:
            new_mf = project.create_managed_folder(_FOLDER_NAME)
            raw: str | None = (
                getattr(new_mf, "id", None)
                or getattr(new_mf, "folder_id", None)
                or (getattr(new_mf, "_data", {}) or {}).get("id")
            )
            if not raw:
                raise RuntimeError(f"Could not extract folder id from {new_mf!r}")
            found_id = raw
        except Exception as e:
            raise RuntimeError(
                f"Could not create DSS managed folder '{_FOLDER_NAME}'. "
                "Either create it manually in the DSS UI and set 'documents_folder_id' "
                f"in Settings, or ensure the project has a writable connection. Error: {e}"
            ) from e

    settings_service.update_settings({"documents_folder_id": found_id})
    _cached_folder_id = found_id
    return found_id


def _folder():
    """Return the DSSManagedFolder handle (resolve id on first call)."""
    from fastapi import HTTPException  # noqa: PLC0415

    try:
        return get_project().get_managed_folder(_resolve_folder_id())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── MIME helpers ───────────────────────────────────────────────────────────────

def _mime_from_ext(ext: str) -> str:
    return _MIME_FROM_EXT.get(ext, "application/octet-stream")


def is_text_mime(mime: str) -> bool:
    return any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES) or mime in _TEXT_MIME_EXACT


def validate_upload(filename: str, content_type: str | None) -> str:
    """Return the resolved MIME type or raise HTTPException(415)."""
    from fastapi import HTTPException  # noqa: PLC0415

    _, raw_ext = os.path.splitext(filename)
    ext = raw_ext.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=415,
            detail=(
                f"File type '{ext or '(none)'}' is not supported. "
                "Accepted: PDF, images, audio, video, and text/code files. "
                "Convert DOCX/XLSX/PPTX to PDF first."
            ),
        )
    mime = (content_type or "").split(";")[0].strip().lower()
    if not mime or mime == "application/octet-stream":
        mime = _mime_from_ext(ext)
    return mime


# ── Document dataclass ─────────────────────────────────────────────────────────

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Document:
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    description: str | None
    status: Literal["describing", "ready", "failed"]
    error: str | None
    uploaded_at: str
    described_at: str | None


def _row_to_doc(row) -> Document:
    return Document(
        id=row["id"],
        filename=row["filename"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        description=row["description"],
        status=row["status"],
        error=row["error"],
        uploaded_at=row["uploaded_at"],
        described_at=row["described_at"],
    )


# ── CRUD ───────────────────────────────────────────────────────────────────────

def create_document(
    filename: str, mime: str, size: int, *, describe: bool = False
) -> Document:
    """Insert a document row.  Status is 'describing' when ENABLE_DESCRIBE is on,
    otherwise 'ready' immediately (no LLM call, no polling needed).
    """
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    status = "describing" if describe else "ready"
    with _lock:
        get_conn().execute(
            "INSERT INTO documents "
            "(id, filename, mime_type, size_bytes, description, status, error, uploaded_at, described_at)"
            " VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, NULL)",
            (doc_id, filename, mime, size, status, now),
        )
    return Document(
        id=doc_id, filename=filename, mime_type=mime, size_bytes=size,
        description=None, status=status, error=None,
        uploaded_at=now, described_at=None,
    )


def set_description(doc_id: str, description: str) -> None:
    with _lock:
        get_conn().execute(
            "UPDATE documents SET description=?, status='ready', described_at=? WHERE id=?",
            (description, _now_iso(), doc_id),
        )


def set_failed(doc_id: str, error: str) -> None:
    with _lock:
        get_conn().execute(
            "UPDATE documents SET status='failed', error=? WHERE id=?",
            (error[:2000], doc_id),
        )


def list_documents() -> list[Document]:
    with _lock:
        rows = get_conn().execute(
            "SELECT * FROM documents ORDER BY uploaded_at DESC"
        ).fetchall()
    return [_row_to_doc(r) for r in rows]


def get_document(doc_id: str) -> Document | None:
    with _lock:
        row = get_conn().execute(
            "SELECT * FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
    return _row_to_doc(row) if row else None


def get_document_by_filename(filename: str) -> Document | None:
    """Look up a document by its exact filename (used by the chatbot tool)."""
    with _lock:
        row = get_conn().execute(
            "SELECT * FROM documents WHERE filename=? ORDER BY uploaded_at DESC LIMIT 1",
            (filename,),
        ).fetchone()
    return _row_to_doc(row) if row else None


def rename_document(doc_id: str, new_filename: str) -> Document:
    """Rename in DSS folder + SQLite. Extension must stay the same.

    DSS managed folders have no native rename API — we copy + delete.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    new_filename = (new_filename or "").strip()
    if not new_filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty.")
    if "/" in new_filename or "\\" in new_filename:
        raise HTTPException(status_code=400, detail="Filename cannot contain path separators.")

    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if new_filename == doc.filename:
        return doc

    old_ext = os.path.splitext(doc.filename)[1].lower()
    new_ext = os.path.splitext(new_filename)[1].lower()
    if new_ext != old_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Extension must stay '{old_ext}' to preserve the file type.",
        )

    folder = _folder()
    resp = folder.get_file(doc.filename)
    folder.put_file(new_filename, resp.content)
    try:
        folder.delete_file(doc.filename)
    except Exception:
        pass

    with _lock:
        get_conn().execute(
            "UPDATE documents SET filename=? WHERE id=?", (new_filename, doc_id)
        )

    updated = get_document(doc_id)
    assert updated is not None
    return updated


def delete_document(doc_id: str) -> None:
    doc = get_document(doc_id)
    if not doc:
        return
    try:
        _folder().delete_file(doc.filename)
    except Exception:
        pass
    with _lock:
        get_conn().execute("DELETE FROM documents WHERE id=?", (doc_id,))


def download_bytes(doc_id: str) -> tuple[bytes, str]:
    doc = get_document(doc_id)
    if not doc:
        raise FileNotFoundError(f"Document {doc_id} not found")
    resp = _folder().get_file(doc.filename)
    return resp.content, doc.mime_type


# ── PDF rasterisation (used by DESCRIBE and agent read_document tool) ──────────

def _rasterize_pdf(data: bytes, max_pages: int) -> tuple[list[dict], int, int]:
    """Render PDF pages to JPEG image_url blocks via PyMuPDF (fitz).

    Returns (blocks, pages_rendered, total_pages).
    Only imported when ENABLE_DESCRIBE=1 or a chatbot agent reads a PDF.
    """
    import base64  # noqa: PLC0415
    import fitz  # type: ignore[import]  # noqa: PLC0415 — pymupdf, lazy import

    blocks: list[dict] = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
        if pdf.is_encrypted:
            try:
                pdf.authenticate("")
            except Exception:
                pass
        if pdf.is_encrypted:
            return [], 0, len(pdf)
        total = len(pdf)
        rendered = min(total, max_pages)
        for i in range(rendered):
            try:
                pix = pdf[i].get_pixmap(matrix=fitz.Matrix(2, 2))
                img = pix.tobytes("jpeg", jpg_quality=85)
                b64 = base64.b64encode(img).decode()
                blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
            except Exception:
                continue
    return blocks, rendered, total


def read_document_blocks(doc_id: str, *, max_pdf_pages: int = 10) -> list[dict]:
    """Return a document's content as LLM-ready multimodal blocks.

    Mirrors the describer's content handling: text files become a text block,
    PDFs are rasterised to image blocks, images become an image_url block, and
    other binaries fall back to a metadata text block. Used by the chatbot
    ``read_document`` tool. Heavy imports (fitz, base64) stay lazy via
    ``_rasterize_pdf``.
    """
    doc = get_document(doc_id)
    if not doc:
        return [{"type": "text", "text": f"Document id '{doc_id}' not found."}]

    try:
        data, mime = download_bytes(doc_id)
    except Exception as e:
        return [{"type": "text", "text": f"Could not read '{doc.filename}': {e}"}]

    if is_text_mime(mime):
        text = data.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
        return [{"type": "text", "text": f"File: {doc.filename}\n\n{text}"}]

    if mime == "application/pdf":
        pages, rendered, total = _rasterize_pdf(data, max_pages=max_pdf_pages)
        if not pages:
            return [{
                "type": "text",
                "text": f"'{doc.filename}' is a PDF that could not be rendered (encrypted or empty).",
            }]
        intro = f"'{doc.filename}': first {rendered} of {total} page(s) rendered as images."
        return [{"type": "text", "text": intro}, *pages]

    if mime.startswith("image/"):
        import base64  # noqa: PLC0415

        b64 = base64.b64encode(data).decode()
        return [
            {"type": "text", "text": f"Image: {doc.filename}"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]

    desc = doc.description or "(no description)"
    return [{
        "type": "text",
        "text": (
            f"'{doc.filename}' ({mime}, {doc.size_bytes} bytes) is not a text, PDF, or "
            f"image file, so its raw content can't be read inline. Description: {desc}"
        ),
    }]

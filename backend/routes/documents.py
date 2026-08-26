"""Documents block — REST endpoints.

Enabled when ``ENABLE_DOCUMENTS=1`` in app.env.
Registered conditionally in ``backend/app.py::configure()``.

Endpoints:
  GET    /api/documents            — list all documents (metadata only)
  POST   /api/documents            — upload one or more files (multipart)
  PATCH  /api/documents/{id}       — rename a document
  DELETE /api/documents/{id}       — delete from folder + DB
  GET    /api/documents/{id}/raw   — download file bytes
  POST   /api/documents/{id}/redescribe  — re-trigger LLM describe (ENABLE_DESCRIBE only)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import config
from ..services import documents_service

router = APIRouter(prefix="/api/documents")


def _doc_dict(doc: documents_service.Document) -> dict[str, Any]:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "mime_type": doc.mime_type,
        "size_bytes": doc.size_bytes,
        "description": doc.description,
        "status": doc.status,
        "error": doc.error,
        "uploaded_at": doc.uploaded_at,
        "described_at": doc.described_at,
    }


@router.get("")
def list_documents() -> list[dict[str, Any]]:
    return [_doc_dict(d) for d in documents_service.list_documents()]


@router.post("")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> list[dict[str, Any]]:
    # Resolve the folder once before the loop so a 503 is returned early.
    folder = documents_service._folder()

    created = []
    for f in files:
        filename = f.filename or "file"
        mime = documents_service.validate_upload(filename, f.content_type)
        data = await f.read()
        try:
            folder.put_file(filename, data)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"DSS upload failed: {e}")

        doc = documents_service.create_document(
            filename, mime, len(data), describe=config.ENABLE_DESCRIBE
        )
        if config.ENABLE_DESCRIBE:
            from ..services.document_describer import describe_document  # noqa: PLC0415
            background_tasks.add_task(describe_document, doc.id)

        created.append(_doc_dict(doc))

    return created


@router.patch("/{doc_id}")
def rename_document(
    doc_id: str, payload: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    new_filename = (payload.get("filename") or "").strip()
    doc = documents_service.rename_document(doc_id, new_filename)
    return _doc_dict(doc)


@router.delete("/{doc_id}")
def delete_document(doc_id: str) -> dict[str, Any]:
    if not documents_service.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    documents_service.delete_document(doc_id)
    return {"ok": True}


@router.get("/{doc_id}/raw")
def download_document_raw(doc_id: str) -> StreamingResponse:
    doc = documents_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        resp = documents_service._folder().get_file(doc.filename)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    data = resp.content

    def _iter():
        yield data

    return StreamingResponse(
        _iter(),
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.post("/{doc_id}/redescribe")
def redescribe_document(
    doc_id: str, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """Re-trigger LLM auto-describe. Only meaningful when ENABLE_DESCRIBE=1."""
    if not config.ENABLE_DESCRIBE:
        raise HTTPException(
            status_code=400,
            detail="ENABLE_DESCRIBE is off — auto-describe is not active.",
        )
    if not documents_service.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")

    from ..services.db import get_conn  # noqa: PLC0415
    from ..services.document_describer import describe_document  # noqa: PLC0415

    get_conn().execute(
        "UPDATE documents SET status='describing', error=NULL WHERE id=?", (doc_id,)
    )
    background_tasks.add_task(describe_document, doc_id)
    return {"ok": True}

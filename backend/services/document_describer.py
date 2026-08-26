"""Background task: ask the app LLM to write a description for an uploaded document.

Only active when ENABLE_DESCRIBE=1.  Requires langchain-core and (for PDFs)
pymupdf — both are lazy-imported inside the function so the module is safe to
import even when those packages are absent (they are never imported unless this
task actually runs).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Write a 1–3 sentence description of this document, focused on what it contains "
    "and what a data scientist or analyst using this application might find useful in it. "
    "Be concrete: mention key topics, entities, time ranges, or data types. "
    "No preamble — just the description."
)
MAX_TEXT_FOR_DESCRIBE = 16_000


def describe_document(doc_id: str) -> None:
    """Fetch the document, build a prompt, invoke the LLM, and persist the result.

    Designed to run as a FastAPI BackgroundTask — all exceptions are caught and
    stored as a 'failed' status so the caller always gets a response immediately.
    """
    from .documents_service import (  # noqa: PLC0415
        get_document,
        set_description,
        set_failed,
        download_bytes,
        is_text_mime,
    )
    from . import settings as settings_service  # noqa: PLC0415

    doc = get_document(doc_id)
    if not doc:
        return

    try:
        data, mime = download_bytes(doc_id)
    except Exception as e:
        set_failed(doc_id, f"Could not fetch file: {e}")
        return

    try:
        settings = settings_service.get_settings()
        llm_id = settings.get("llm_id")
        if not llm_id:
            set_failed(doc_id, "No LLM configured — pick one in Settings.")
            return

        from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415
        from ..dss_client import get_project  # noqa: PLC0415

        model = get_project().get_llm(llm_id).as_langchain_chat_model()

        if is_text_mime(mime):
            text = data.decode("utf-8", errors="replace")[:MAX_TEXT_FOR_DESCRIBE]
            content: str | list = f"File: {doc.filename}\n\n{text}"

        elif mime == "application/pdf":
            from .documents_service import _rasterize_pdf  # noqa: PLC0415
            pages, rendered, total = _rasterize_pdf(data, max_pages=5)
            if not pages:
                content = (
                    f"File: {doc.filename} (PDF, {doc.size_bytes} bytes). "
                    "Could not render pages (encrypted or empty). Describe based on filename only."
                )
            else:
                intro = (
                    f"Please describe this PDF named '{doc.filename}'. "
                    f"You are seeing the first {rendered} of {total} page(s) rendered as images."
                )
                content = [{"type": "text", "text": intro}, *pages]

        elif mime.startswith("image/"):
            import base64  # noqa: PLC0415
            b64 = base64.b64encode(data).decode()
            content = [
                {"type": "text", "text": f"Please describe this image: '{doc.filename}'."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]

        else:
            # Audio/video/binary: describe from filename + MIME alone
            content = (
                f"File: {doc.filename} (type: {mime}). "
                "Based on the filename and file type, write a brief description of what this file likely contains."
            )

        messages = [SystemMessage(content=_SYSTEM), HumanMessage(content=content)]
        response = model.invoke(messages)
        description = (response.content or "").strip() or f"{doc.filename} ({mime})"
        set_description(doc_id, description)

    except Exception as e:
        logger.exception("describe_document failed for %s", doc_id)
        set_failed(doc_id, str(e)[:2000])

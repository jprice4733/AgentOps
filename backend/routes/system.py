"""System endpoints: health check, available LLMs, app settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..dss_client import get_project
from ..services import settings as settings_service

router = APIRouter(prefix="/api/system")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/llms")
def list_llms() -> list[dict[str, Any]]:
    """Return LLMs available in the current DSS project for GENERIC_COMPLETION."""
    try:
        project = get_project()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not connect to DSS: {e}")
    try:
        items = project.list_llms(purpose="GENERIC_COMPLETION")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DSS list_llms failed: {e}")
    out: list[dict[str, Any]] = []
    for it in items:
        raw: dict[str, Any] = getattr(it, "_data", {}) or {}
        out.append({
            "id": raw.get("id", ""),
            "label": raw.get("friendlyName") or raw.get("name") or raw.get("id", ""),
            "type": raw.get("type") or "",
            "provider": raw.get("provider") or "",
        })
    return out


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    try:
        return settings_service.get_settings()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.put("/settings")
def update_settings(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return settings_service.update_settings(patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

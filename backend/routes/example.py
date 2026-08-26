"""Example routes — list project datasets and preview rows.

Demonstrates the full FE ↔ BE ↔ DSS path:
  - GET /api/example/datasets   list all datasets in the project
  - GET /api/example/preview    fetch up to `limit` rows from a named dataset

Delete or replace with your own domain routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..dss_client import get_dataiku, get_project

router = APIRouter(prefix="/api/example")


@router.get("/datasets")
def list_datasets() -> list[dict[str, Any]]:
    """Return all datasets visible in the current DSS project."""
    try:
        project = get_project()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not connect to DSS: {e}")

    result: list[dict[str, Any]] = []
    for ds in project.list_datasets():
        if isinstance(ds, dict):
            result.append({"name": ds.get("name", ""), "type": ds.get("type", "")})
        else:
            result.append({"name": str(ds), "type": ""})
    return result


@router.get("/preview")
def preview_dataset(
    name: str = Query(..., description="Dataset name"),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """Return up to `limit` rows from the named dataset, as pandas via
    ``dataiku.Dataset.get_dataframe()`` (in-DSS, or local dev against the remote
    instance through the installed ``dataiku-internal-client`` — see ``get_dataiku``).
    """
    try:
        df = get_dataiku().Dataset(name).get_dataframe(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dataset preview failed: {e}")

    # Map pandas dtypes to short DSS-style type names for the UI schema icons.
    def _dtype_to_type(dtype: Any) -> str:
        name = str(dtype)
        if name == "object" or name == "string":
            return "string"
        if name.startswith("int"):
            return "bigint"
        if name.startswith("float"):
            return "double"
        if name.startswith("bool"):
            return "boolean"
        if name.startswith("datetime"):
            return "date"
        return name

    schema = {col: _dtype_to_type(df[col].dtype) for col in df.columns}
    return {
        "columns": list(df.columns),
        "rows": df.head(limit).where(df.notna(), None).values.tolist(),
        "row_count": len(df),
        "schema": schema,
    }

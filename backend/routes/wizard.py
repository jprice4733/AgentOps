"""Wizard block — a multi-step guided creation flow.

Hello-world example of a "create something step by step" wizard:
  - POST /api/wizard/submit   validate the collected fields, return a result

This route is intentionally **self-contained** (no DSS, no persistence) so the
block renders with zero configuration.  To make it real, persist the payload
where marked below (a project variable, a dataset write, an external API call).

Optional block — registered only when ENABLE_WIZARD=1 (see backend/app.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter

router = APIRouter(prefix="/api/wizard")


class WizardSubmission(BaseModel):
    """Payload collected across the wizard steps."""

    name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(..., min_length=1)
    notes: str = Field("", max_length=2000)


class WizardResult(BaseModel):
    id: str
    summary: str


@router.post("/submit", response_model=WizardResult)
def submit(payload: WizardSubmission) -> WizardResult:
    """Validate the wizard payload and return a confirmation.

    Pydantic validates ``payload`` before this body runs, so an empty name or
    missing category returns a 422 automatically — the frontend surfaces it.
    """
    # ── Persist here in a real app ────────────────────────────────────────────
    # e.g. get_project().get_variables() + set_variables(), or write to a
    # dataset.  Kept stateless so the hello-world boots without DSS.
    short_id = f"{payload.category[:3].lower()}-{abs(hash(payload.name)) % 100000:05d}"
    summary = f'Created "{payload.name}" in category "{payload.category}".'
    return WizardResult(id=short_id, summary=summary)

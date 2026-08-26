"""Agents block — card-grid example for the Administration section.

GET /api/agents/sample  returns a small list of agents to render as cards.

This route is intentionally **self-contained** (no DSS) so the block renders
with zero configuration.  To make it real, replace the static list with e.g.
the project's DSS agents (project.list_agents() via the Python API) or any
domain entities you want to present as a card grid.

Always registered — the Administration section's visibility is controlled at
runtime by the Admin sidebar toggle (frontend/src/stores/admin.ts), not by an
ENABLE_* flag.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents")


class Agent(BaseModel):
    id: str
    name: str
    description: str
    status: str  # "active" | "paused" | "error"
    model: str
    runs_today: int
    last_run: str  # human-readable, e.g. "12 min ago"


@router.get("/sample", response_model=list[Agent])
def sample_agents() -> list[Agent]:
    """Return hardcoded sample agents for the card-grid view.

    Replace with your domain entities (DSS agents, scheduled jobs, etc.).
    """
    return [
        Agent(
            id="triage",
            name="Alert Triage",
            description="Classifies incoming alerts and routes them to the right queue.",
            status="active",
            model="gpt-4o-mini",
            runs_today=128,
            last_run="2 min ago",
        ),
        Agent(
            id="summarizer",
            name="Daily Digest",
            description="Summarises overnight activity into a morning briefing.",
            status="active",
            model="claude-sonnet-4-6",
            runs_today=1,
            last_run="6 h ago",
        ),
        Agent(
            id="enricher",
            name="Record Enricher",
            description="Augments new CRM records with firmographic data.",
            status="active",
            model="gpt-4o-mini",
            runs_today=342,
            last_run="just now",
        ),
        Agent(
            id="qa-bot",
            name="Docs Q&A",
            description="Answers product questions from the internal knowledge base.",
            status="paused",
            model="claude-haiku-4-5",
            runs_today=0,
            last_run="3 days ago",
        ),
        Agent(
            id="anomaly",
            name="Anomaly Watcher",
            description="Flags unusual patterns in pipeline metrics every 15 minutes.",
            status="error",
            model="gpt-4o",
            runs_today=17,
            last_run="42 min ago",
        ),
        Agent(
            id="translator",
            name="Ticket Translator",
            description="Translates inbound support tickets to English before routing.",
            status="active",
            model="claude-haiku-4-5",
            runs_today=56,
            last_run="11 min ago",
        ),
    ]

"""App settings persisted as DSS project variables.

The entire payload lives under a single project-variable key so one DSS
write covers every change. Only ALLOWED_KEYS are read/written for safety.

Key is scoped by APP_PREFIX so two webapps in the same project don't collide.
"""

from __future__ import annotations

from typing import Any

from ..config import PREFIX
from ..dss_client import get_project

# Project variable key — derived from the app prefix.
VARIABLE_KEY = f"{PREFIX.lower()}_app_settings"

# Whitelist of settings keys. Extend as needed.
# Keys are split by concern — the blocks only add keys when active, but the
# whitelist is always present to avoid a "unknown key" error if a partial
# settings update is sent while a block is transitioning.
ALLOWED_KEYS: frozenset[str] = frozenset({
    "llm_id",
    # ── Documents block ──────────────────────────────────────────────────────
    # Cached resolved id of the DSS managed folder (set automatically on first
    # upload; override manually if auto-creation fails on your instance).
    "documents_folder_id",
    # ── Chatbot block ────────────────────────────────────────────────────────
    # Per-tool policy: {"tool_name": "allow" | "prompt"}.
    "tool_permissions",
    # When true the agent executes all tools without asking (use with care).
    "accept_all_mode",
})

# Default tool policy — allow read-only tools, prompt on mutating ones.
# The chatbot block imports this at startup; inert when ENABLE_CHATBOT=0.
DEFAULT_TOOL_POLICY: dict[str, str] = {
    # ── Core DSS tools (all read-only, always allow) ──────────────────────────
    "list_datasets": "allow",
    "inspect_dataset": "allow",
    "sample_data": "allow",
    "search_knowledge_base": "allow",
    # ── Mutating demo tool (prompt so the approval flow is exercised) ──────────
    "create_scratch_note": "prompt",
    # ── Documents block tools (inert when ENABLE_DOCUMENTS=0) ─────────────────
    "list_documents": "allow",
    "read_document": "allow",
}


def _blank() -> dict[str, Any]:
    return {
        "llm_id": None,
        "documents_folder_id": None,
        "tool_permissions": dict(DEFAULT_TOOL_POLICY),
        "accept_all_mode": False,
    }


def decide(tool_name: str) -> str:
    """Return 'allow' or 'prompt' for the given tool, consulting stored policy.

    Falls back to 'prompt' for any unknown tool (safe default).
    """
    settings = get_settings()
    if settings.get("accept_all_mode"):
        return "allow"
    policy: dict[str, str] = settings.get("tool_permissions") or {}
    return policy.get(tool_name, "prompt")


def set_tool_permission(tool_name: str, decision: str) -> None:
    """Persist 'allow' or 'prompt' for a single tool (called by 'remember' in broker)."""
    settings = get_settings()
    policy: dict[str, str] = dict(settings.get("tool_permissions") or DEFAULT_TOOL_POLICY)
    policy[tool_name] = decision
    update_settings({"tool_permissions": policy})


def get_settings() -> dict[str, Any]:
    project = get_project()
    standard: dict[str, Any] = project.get_variables().get("standard", {})
    stored: dict[str, Any] = standard.get(VARIABLE_KEY) or {}
    return {**_blank(), **{k: v for k, v in stored.items() if k in ALLOWED_KEYS}}


def update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    unknown = set(patch) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"Unknown settings keys: {sorted(unknown)}")

    project = get_project()
    variables: dict[str, Any] = project.get_variables()
    standard = variables.setdefault("standard", {})
    current: dict[str, Any] = dict(standard.get(VARIABLE_KEY) or {})
    current.update({k: v for k, v in patch.items() if k in ALLOWED_KEYS})
    standard[VARIABLE_KEY] = current
    project.set_variables(variables)
    return {**_blank(), **current}

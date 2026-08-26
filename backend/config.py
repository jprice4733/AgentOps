"""Central config — reads from environment variables set by the Makefile
(via app.env) or by dss_webapp/backend.py in DSS.

All env vars are prefixed by APP_PREFIX (set by the Makefile via app.env, or by
dss_webapp/backend.py in DSS) so multiple webapps deployed to the same project
don't collide.
"""

from __future__ import annotations

import os

# The prefix drives all other env-var names.  In local dev it comes from
# app.env (exported by the Makefile). In DSS it is set explicitly by
# dss_webapp/backend.py before importing configure().
PREFIX: str = os.environ.get("APP_PREFIX", "")

# DSS project key — used by dss_client when running outside DSS.
PROJECT_KEY: str = os.environ.get("PROJECT_KEY", "")

# True when running inside a DSS webapp backend.
DSS_MODE: bool = bool(os.environ.get(f"{PREFIX}_DSS_MODE"))

# Log level for the Python logger.
LOG_LEVEL: str = os.environ.get(f"{PREFIX}_LOG_LEVEL", "INFO")

# Allowed CORS origins for local dev (the Vite dev server).
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.environ.get(
        f"{PREFIX}_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]


# ── Optional building blocks ───────────────────────────────────────────────────
# Flags are UNPREFIXED so they survive a rename (which only rewrites
# APP_PREFIX/LIB_NS lines).  We use a strict parser instead of the bare
# bool(os.environ.get(...)) idiom because that treats "0" and "false" as
# truthy — a footgun when operators explicitly turn something off.

def _flag(name: str) -> bool:
    """Return True only for explicit "on" values; "0"/"false" → False."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


ENABLE_DOCUMENTS: bool = _flag("ENABLE_DOCUMENTS")
ENABLE_CHATBOT: bool = _flag("ENABLE_CHATBOT")

# Sub-option of DOCUMENTS: LLM auto-describe (pulls langchain-core + pymupdf).
# Kept separate so a team can enable document storage without the heavy deps.
ENABLE_DESCRIBE: bool = _flag("ENABLE_DESCRIBE")

# ── Self-contained blocks (no DSS / no persistence required) ──────────────────
# These render with zero configuration and are safe to leave on by default.
# NB: ENABLE_CHARTS is a frontend-only flag (charts use mock data, no backend
# route), so it is read by the Vite build, not here.
ENABLE_WIZARD: bool = _flag("ENABLE_WIZARD")
ENABLE_FLOW: bool = _flag("ENABLE_FLOW")

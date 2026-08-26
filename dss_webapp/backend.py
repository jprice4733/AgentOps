"""DSS webapp backend entry point.

DSS 14.4+ runs FastAPI natively (no a2wsgi wrapper needed). The project
library's python/ directory is on sys.path once deploy.sh has pushed the
source to python/<LIB_NS>/backend/.

Source of truth is app.env. This file is NOT what `make deploy` runs — deploy.sh
generates the webapp's inline Python from app.env's LIB_NS/APP_PREFIX. The literals
below are only a fallback for running this module directly; keep them in sync with
app.env if you rely on that path.
"""

import importlib
import os

# Fallback values for direct entry only — the deployed webapp gets these from
# app.env via deploy.sh. Keep in sync with app.env LIB_NS / APP_PREFIX if used.
LIB_NS = "blueprint"
APP_PREFIX = "BLUEPRINT"

# Set APP_PREFIX in the process env so backend/config.py can read it via
# os.environ.get("APP_PREFIX").  Must come before importing configure().
os.environ["APP_PREFIX"] = APP_PREFIX
os.environ[f"{APP_PREFIX}_DSS_MODE"] = "1"
os.environ.setdefault(f"{APP_PREFIX}_CORS_ORIGINS", "*")

# LIB_NS is needed by the optional SQLite persistence layer to derive its
# snapshot path (python/<LIB_NS>/state.db) in the DSS project library.
os.environ["LIB_NS"] = LIB_NS

# Optional building block flags — set to "1" to enable.
# (deploy.sh injects the real values from app.env into the generated
# inline python; these setdefault calls are a fallback for direct entry.)
os.environ.setdefault("ENABLE_WIZARD", "0")
os.environ.setdefault("ENABLE_CHARTS", "0")
os.environ.setdefault("ENABLE_FLOW", "0")
os.environ.setdefault("ENABLE_DOCUMENTS", "0")
os.environ.setdefault("ENABLE_CHATBOT", "0")
os.environ.setdefault("ENABLE_DESCRIBE", "0")

# `app` is injected as a global by DSS before this code runs.
importlib.import_module(f"{LIB_NS}.backend.app").configure(app)  # type: ignore[name-defined]  # noqa: F821

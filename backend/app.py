"""FastAPI backend entry point.

Local dev:
    uvicorn backend.app:app --reload --host 127.0.0.1 --port 5000

DSS webapp:
    dss_webapp/backend.py calls configure(app) on the DSS-injected FastAPI
    instance after the project library puts this package on sys.path.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from . import config

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes.agents import router as agents_router
from .routes.example import router as example_router
from .routes.system import router as system_router

# Optional block routers are imported lazily inside configure() so that a
# disabled block never imports langchain / pymupdf (which may be absent from
# the code env when the block is off).

logger = logging.getLogger(__name__)


def _find_dist_dir() -> Path | None:
    """Locate the built frontend.

    1. DSS library path: sibling ``frontend_dist/`` next to this package.
    2. Local repo:       ``<repo>/frontend/dist/``.
    """
    dss_dist = Path(__file__).resolve().parent.parent / "frontend_dist"
    if dss_dist.is_dir():
        return dss_dist
    local_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if local_dist.is_dir():
        return local_dist
    return None


def configure(app: FastAPI) -> None:
    """Wire CORS, routes, and (in DSS) static SPA serving onto a FastAPI app."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(system_router)
    app.include_router(example_router)
    # Agents card-grid blueprint — always on; the sidebar's Administration
    # section toggle (frontend) controls its visibility at runtime.
    app.include_router(agents_router)

    # ── Optional building blocks ───────────────────────────────────────────────
    # Each block is activated by an env flag (set in app.env).
    # The router import lives inside the guard so the block's heavy dependencies
    # (langchain-core, pymupdf, python-multipart) are never imported when the
    # block is disabled — safe to run even if the package is not installed.

    if config.ENABLE_DOCUMENTS:
        from .routes.documents import router as documents_router  # noqa: PLC0415
        app.include_router(documents_router)
        logger.info("Documents block enabled")

    if config.ENABLE_CHATBOT:
        from .routes.chat import router as chat_router  # noqa: PLC0415
        app.include_router(chat_router)
        logger.info("Chatbot block enabled")

    if config.ENABLE_WIZARD:
        from .routes.wizard import router as wizard_router  # noqa: PLC0415
        app.include_router(wizard_router)
        logger.info("Wizard block enabled")

    if config.ENABLE_FLOW:
        from .routes.flow import router as flow_router  # noqa: PLC0415
        app.include_router(flow_router)
        logger.info("Flow block enabled")

    # ── Per-user impersonation (opt-in) ───────────────────────────────────────
    # Uncomment to enforce row-level DSS permissions in every request.
    # The backend runs as the DSS service account by default; this resolves
    # the calling browser user and wraps DSS calls with their identity.
    #
    # @app.middleware("http")
    # async def impersonate(request: Request, call_next):
    #     from fastapi import Request as Req
    #     import dataiku
    #     auth = dataiku.api_client().get_auth_info_from_browser_headers(
    #         dict(request.headers)
    #     )
    #     with dataiku.WebappImpersonationContext(auth["authIdentifier"]):
    #         return await call_next(request)

    # ── Static frontend serving (DSS only) ───────────────────────────────────
    # Only mount the SPA when running inside DSS — in local dev, Vite's dev
    # server serves the frontend and proxies /api to this backend.
    if config.DSS_MODE:
        dist_dir = _find_dist_dir()
        if dist_dir:
            logger.info("Serving frontend from %s", dist_dir)

            if (dist_dir / "assets").is_dir():
                app.mount(
                    "/assets",
                    StaticFiles(directory=dist_dir / "assets"),
                    name="static-assets",
                )

            for static_file in dist_dir.glob("*.*"):
                if static_file.name == "index.html" or not static_file.is_file():
                    continue
                _path = str(static_file)

                @app.get(f"/{static_file.name}")
                async def _serve_root(p: str = _path) -> FileResponse:
                    return FileResponse(p)

            @app.get("/{path:path}")
            async def spa_fallback(path: str) -> FileResponse:
                return FileResponse(dist_dir / "index.html")


# Module-level app for `uvicorn backend.app:app` (local dev).
app = FastAPI(title=os.environ.get("VITE_APP_NAME") or "App")
configure(app)

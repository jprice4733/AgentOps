"""Dual-mode DSS project accessor.

Inside DSS (webapp backend):  dataiku.api_client().get_default_project()
Local dev:                     dataikuapi.DSSClient from ~/.dataiku/config.json
                               (instance picked by DKU_INSTANCE in app.env,
                               falling back to the file's default_instance)
Fallback:                      DSS_URL + DSS_API_KEY env vars.

Environment detection is the ``DSS_MODE`` flag (set by dss_webapp/backend.py in
DSS, never set locally) — NOT ``import dataiku`` success, because local dev
installs the real ``dataiku`` (``dataiku-internal-client``, see ``get_dataiku``
and pyproject.toml), so ``import dataiku`` succeeds locally and would otherwise be
mistaken for in-DSS.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import config


def _local_creds() -> tuple[str, str]:
    """(url, api_key) for the configured instance.

    Read from ~/.dataiku/config.json (instance picked by DKU_INSTANCE, falling
    back to the file's default_instance) or from DSS_URL + DSS_API_KEY env vars.
    """
    cfg_path = Path.home() / ".dataiku" / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        name = os.environ.get("DKU_INSTANCE") or cfg.get("default_instance", "default")
        inst = cfg["dss_instances"][name]
        return inst["url"].rstrip("/"), inst["api_key"]

    return os.environ["DSS_URL"], os.environ["DSS_API_KEY"]


def _local_client():
    """Build a dataikuapi client from ~/.dataiku/config.json or env vars."""
    import dataikuapi

    url, key = _local_creds()
    return dataikuapi.DSSClient(url, key)


def get_project():
    """Return a DSSProject handle for the current or configured project."""
    if config.DSS_MODE:
        import dataiku  # only available inside DSS

        return dataiku.api_client().get_default_project()

    return _local_client().get_project(config.PROJECT_KEY)


_remote_ready = False


def get_dataiku():
    """The configured ``dataiku`` module (always available).

    - Inside DSS (``DSS_MODE``): the runtime ``dataiku`` module, already configured.
    - Local dev: the installed ``dataiku-internal-client`` (a required dev dependency,
      see pyproject.toml) wired to the remote instance, so
      ``dataiku.Dataset(...).get_dataframe()`` works exactly like in-DSS.

    Run ``uv sync`` if ``import dataiku`` fails locally — the package is required.
    """
    import dataiku

    if config.DSS_MODE:
        return dataiku

    global _remote_ready
    if not _remote_ready:
        url, key = _local_creds()
        dataiku.set_remote_dss(url, key)
        dataiku.set_default_project_key(config.PROJECT_KEY)
        _remote_ready = True
    return dataiku

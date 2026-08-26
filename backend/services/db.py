"""Shared SQLite store for the optional building blocks (Documents + Chatbot).

Single-file database at ``<repo>/.run/state.db`` in local dev, or the DSS
workload-local folder when running inside DSS.  Override the path with the
``{PREFIX}_DB_PATH`` env var.

The connection is process-shared (``check_same_thread=False``); serialised
writes are done via the ``RLock`` in the block-level service modules (SQLite
itself serialises via WAL mode).

**Schema migrations: this is a prototype — bump the schema by deleting the DB
file.  There is no migration runner.**

Connection is lazy: ``get_conn()`` is only ever called from routes/services
of enabled blocks.  When both blocks are disabled, no route imports this
module, no ``state.db`` file is ever created, and the base template boots
identically to before.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..config import PREFIX

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / ".run" / "state.db"


def _resolve_db_path() -> Path:
    override = os.environ.get(f"{PREFIX}_DB_PATH")
    if override:
        return Path(override).expanduser().resolve()
    if os.environ.get(f"{PREFIX}_DSS_MODE"):
        try:
            from dataiku.core.workload_local_folder import get_workload_local_folder_path  # type: ignore[import]
            return Path(get_workload_local_folder_path()) / "state.db"
        except Exception:
            pass
    return _DEFAULT_DB_PATH


DB_PATH: Path = _resolve_db_path()

# ── Schema ─────────────────────────────────────────────────────────────────────
# Three tables — one per block, plus conversations/messages for the chatbot.
# All tables are created unconditionally (idempotent IF NOT EXISTS); having an
# empty table for a disabled block is harmless and simpler than composing the
# schema dynamically.

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id               TEXT PRIMARY KEY,
  conversation_id  TEXT NOT NULL,
  role             TEXT NOT NULL,
  content          TEXT,
  tool_calls_json  TEXT,
  tool_call_id     TEXT,
  created_at       TEXT NOT NULL,
  position         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_conversation
  ON messages(conversation_id, position);

CREATE TABLE IF NOT EXISTS documents (
  id            TEXT PRIMARY KEY,
  filename      TEXT NOT NULL,
  mime_type     TEXT NOT NULL,
  size_bytes    INTEGER NOT NULL,
  description   TEXT,
  status        TEXT NOT NULL,
  error         TEXT,
  uploaded_at   TEXT NOT NULL,
  described_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_documents_status ON documents(status);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
        isolation_level=None,  # autocommit; explicit BEGIN for transactions
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    """Return the process-wide SQLite connection, opening it on first call."""
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn

"""SQLite-backed state for the chatbot (conversations + messages).

The RLock guards the shared connection because FastAPI dispatches sync routes
to the threadpool while the chat agent loop runs on the event loop — both can
hit the connection concurrently.  SQLite serialises writes via WAL mode.

Schema migrations: bump the schema by deleting ``.run/state.db`` — there is no
migration runner in this prototype.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Literal

from .db import get_conn

_lock = RLock()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class Conversation:
    id: str
    name: str
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class ChatMessage:
    id: str
    conversation_id: str
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    created_at: str = field(default_factory=_now_iso)


# ── Row adapters ───────────────────────────────────────────────────────────────

def _conversation_from_row(row: Any) -> Conversation:
    return Conversation(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _message_from_row(row: Any) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"] or "",
        tool_calls=json.loads(row["tool_calls_json"]) if row["tool_calls_json"] else [],
        tool_call_id=row["tool_call_id"],
        created_at=row["created_at"],
    )


# ── Conversations ──────────────────────────────────────────────────────────────

def create_conversation(name: str | None = None) -> Conversation:
    with _lock:
        conn = get_conn()
        cid = _new_id("conv")
        now = _now_iso()
        conn.execute(
            "INSERT INTO conversations (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, name or "Untitled conversation", now, now),
        )
        return Conversation(id=cid, name=name or "Untitled conversation", created_at=now, updated_at=now)


def get_conversation(conversation_id: str) -> Conversation | None:
    with _lock:
        row = get_conn().execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return _conversation_from_row(row) if row else None


def list_conversations() -> list[Conversation]:
    with _lock:
        rows = get_conn().execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [_conversation_from_row(r) for r in rows]


def update_conversation(conversation_id: str, **patch: Any) -> Conversation | None:
    allowed = {"name"}
    with _lock:
        conn = get_conn()
        cols = [f"{k} = ?" for k in patch if k in allowed]
        vals = [v for k, v in patch.items() if k in allowed]
        if not cols:
            return get_conversation(conversation_id)
        cols.append("updated_at = ?")
        vals.append(_now_iso())
        vals.append(conversation_id)
        cur = conn.execute(f"UPDATE conversations SET {', '.join(cols)} WHERE id = ?", vals)
        if cur.rowcount == 0:
            return None
        return get_conversation(conversation_id)


def delete_conversation(conversation_id: str) -> bool:
    with _lock:
        conn = get_conn()
        if not conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone():
            return False
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return True


# ── Messages ───────────────────────────────────────────────────────────────────

def append_message(
    conversation_id: str,
    role: Literal["user", "assistant", "tool"],
    content: str,
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
) -> ChatMessage:
    with _lock:
        conn = get_conn()
        if not conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone():
            raise KeyError(f"conversation {conversation_id!r} not found")
        pos_row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        position = int(pos_row["pos"])
        msg = ChatMessage(
            id=_new_id("msg"),
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            tool_call_id=tool_call_id,
        )
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, tool_calls_json, "
            "tool_call_id, created_at, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                msg.id, msg.conversation_id, msg.role, msg.content,
                json.dumps(msg.tool_calls) if msg.tool_calls else None,
                msg.tool_call_id, msg.created_at, position,
            ),
        )
        # Update conversation timestamp so list sorts correctly.
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now_iso(), conversation_id),
        )
        return msg


def get_messages(conversation_id: str, *, limit: int | None = None) -> list[ChatMessage]:
    with _lock:
        conn = get_conn()
        if limit is None:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY position",
                (conversation_id,),
            ).fetchall()
        else:
            rows = list(reversed(
                conn.execute(
                    "SELECT * FROM messages WHERE conversation_id = ? "
                    "ORDER BY position DESC LIMIT ?",
                    (conversation_id, int(limit)),
                ).fetchall()
            ))
        return [_message_from_row(r) for r in rows]

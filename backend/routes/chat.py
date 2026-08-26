"""Chatbot block — REST and SSE endpoints.

Enabled when ``ENABLE_CHATBOT=1`` in app.env.
Registered conditionally in ``backend/app.py::configure()``.

Endpoints:
  GET    /api/chat/conversations          — list all conversations
  POST   /api/chat/conversations          — create a conversation
  GET    /api/chat/conversations/{id}     — get one conversation
  PUT    /api/chat/conversations/{id}     — rename
  DELETE /api/chat/conversations/{id}     — delete with its messages
  GET    /api/chat/conversations/{id}/messages — message history
  POST   /api/chat/messages               — submit a user message (SSE stream)
  POST   /api/chat/permissions/{conv}/{call} — resolve a pending tool permission
  GET    /api/chat/tools                  — list available tools + current policy
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..services import chat_agent, memory_state
from ..services import permission_broker as pb
from ..services import settings as settings_service
from ..tools.registry import make_tools

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat")


# ── Conversations ─────────────────────────────────────────────────────────────

@router.get("/conversations")
def list_conversations() -> list[dict[str, Any]]:
    return [_conv_dict(c) for c in memory_state.list_conversations()]


@router.post("/conversations")
def create_conversation(payload: dict[str, Any] = Body({})) -> dict[str, Any]:
    name = (payload.get("name") or "New conversation").strip()
    return _conv_dict(memory_state.create_conversation(name=name))


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
    conv = memory_state.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_dict(conv)


@router.put("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str, payload: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    conv = memory_state.update_conversation(conversation_id, name=payload.get("name", ""))
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_dict(conv)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, Any]:
    pb.broker.cancel_for_conversation(conversation_id)
    if not memory_state.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    if memory_state.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [_msg_dict(m) for m in memory_state.get_messages(conversation_id)]


# ── Chat (SSE) ────────────────────────────────────────────────────────────────

@router.post("/messages")
async def post_message(payload: dict[str, Any] = Body(...)):
    """Submit a user message and stream back agent events via SSE.

    Body: ``{"conversationId"?: str, "text": str}``

    If ``conversationId`` is omitted, a new conversation is created and its id
    is emitted as the first event (``{"type":"conversation", ...}``).
    """
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    conversation_id: str | None = payload.get("conversationId")
    if not conversation_id:
        conversation_id = memory_state.create_conversation(name=_title_from_text(text)).id
    else:
        conv = memory_state.get_conversation(conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # First message into a still-default-named conversation sets its title.
        if conv.name == "New conversation" and not memory_state.get_messages(conversation_id):
            memory_state.update_conversation(conversation_id, name=_title_from_text(text))

    async def event_stream() -> AsyncIterator[dict[str, Any]]:
        yield {"event": "message", "data": json.dumps({"type": "conversation", "conversation_id": conversation_id})}
        try:
            async for ev in chat_agent.run_chat_turn(conversation_id, text):
                yield {"event": "message", "data": json.dumps(ev)}
        except Exception as err:
            logger.exception("[chat] turn failed")
            yield {"event": "message", "data": json.dumps({"type": "error", "message": str(err)})}
        finally:
            pb.broker.cancel_for_conversation(conversation_id)

    return EventSourceResponse(event_stream(), ping=15)


# ── Tool permission resolution ────────────────────────────────────────────────

class PermissionDecision(BaseModel):
    decision: Literal["allow", "deny"]
    remember: bool = False


@router.post("/permissions/{conversation_id}/{call_id}")
async def resolve_permission(
    conversation_id: str, call_id: str, body: PermissionDecision
) -> dict[str, str]:
    """Resolve a pending tool-permission prompt from the UI."""
    ok = pb.broker.resolve(conversation_id, call_id, body.decision, body.remember)
    if not ok:
        raise HTTPException(status_code=409, detail="No pending permission with that id")
    return {"status": "ok"}


# ── Tool introspection ────────────────────────────────────────────────────────

@router.get("/tools")
def list_tools() -> list[dict[str, Any]]:
    """Return available tools with their current allow/prompt policy.

    Used by the Settings UI to render the per-tool policy toggles.
    """
    settings = settings_service.get_settings()
    policy: dict[str, str] = settings.get("tool_permissions") or {}
    tools = make_tools("_introspection")
    return [
        {
            "name": t.name,
            "description": (t.description or "").split("\n")[0],
            "policy": policy.get(t.name, "prompt"),
        }
        for t in tools
    ]


def _title_from_text(text: str) -> str:
    """Derive a conversation title from the first words of a message."""
    title = " ".join(text.split()[:8])[:60].rstrip()
    return title + ("…" if title != text.strip() else "")


# ── Serialisers ───────────────────────────────────────────────────────────────

def _conv_dict(c: memory_state.Conversation) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _msg_dict(m: memory_state.ChatMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "role": m.role,
        "content": m.content,
        "tool_calls": m.tool_calls,
        "tool_call_id": m.tool_call_id,
        "created_at": m.created_at,
    }

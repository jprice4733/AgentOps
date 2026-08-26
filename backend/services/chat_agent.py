"""Streaming chat-agent loop (Chatbot building block).

Runs a model→tool→model loop against the DSS LLM Mesh via LangChain, yielding
SSE-shaped events for the route to serialise for the frontend.

Event schema:
  {"type": "text_delta",          "content": str}
  {"type": "tool_call_started",   "id": str, "name": str, "args": dict}
  {"type": "tool_call_completed", "id": str, "name": str, "args": dict,
                                  "output": str, "ok": bool}
  {"type": "permission_requested","id": str, "name": str, "args": dict}
  {"type": "permission_resolved", "id": str, "decision": str, "remember": bool}
  {"type": "turn_completed",      "message_id": str}
  {"type": "error",               "message": str}

The loop is one-shot: one user turn → one terminal ``turn_completed`` or
``error`` event.  Multi-turn is handled at the route level by loading the full
message history from memory_state before each turn.

**Design notes:**
- LLM access: ``get_project().get_llm(id).as_langchain_chat_model()`` — the
  DSS LLM Mesh handles authentication, routing, and provider abstraction.
- Tool concurrency: approved tools run concurrently via asyncio.gather; an
  asyncio.Queue fans events back in arrival order.
- Permission gating: each tool call is checked against the policy; ``prompt``
  tools suspend the loop awaiting a UI POST to /api/chat/permissions/{conv}/{call}.
- Single-process constraint: this loop shares the event loop with uvicorn;
  sync tool code runs on FastAPI's threadpool via ``await tool.ainvoke()``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncIterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool

from ..dss_client import get_project
from ..tools.registry import make_tools
from . import memory_state
from . import permission_broker as pb
from . import settings as settings_service
from .memory_state import Conversation, ChatMessage

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 100
MAX_HISTORY_MESSAGES = 200
MAX_TOOL_OUTPUT_CHARS = 8_000


# ── LLM client ────────────────────────────────────────────────────────────────

def _chat_model() -> BaseChatModel:
    settings = settings_service.get_settings()
    llm_id = settings.get("llm_id")
    if not llm_id:
        raise ValueError("No LLM selected — pick one in Settings.")
    return get_project().get_llm(llm_id).as_langchain_chat_model()


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(conversation: Conversation) -> str:  # noqa: ARG001
    """Build the system prompt for this turn.

    Intentionally minimal in the blueprint — extend this with domain context,
    dataset schemas, or injected knowledge-base excerpts.
    """
    parts = [
        "You are a helpful assistant integrated with a Dataiku DSS project.",
        "You have access to tools that can query the project's datasets and perform actions.",
        "Be concise and accurate.  Ask for clarification when the user's intent is ambiguous.",
    ]

    # Inject document summaries when the Documents block is also enabled.
    try:
        from .. import config  # noqa: PLC0415
        if config.ENABLE_DOCUMENTS:
            from . import documents_service  # noqa: PLC0415
            ready = [d for d in documents_service.list_documents() if d.status == "ready"]
            if ready:
                parts.append("\nUPLOADED DOCUMENTS (use list_documents / read_document to access):")
                for d in ready:
                    desc = d.description or "(no description)"
                    parts.append(f"  - {d.filename}: {desc}")
    except Exception:
        pass

    return "\n".join(parts)


# ── Message conversion ────────────────────────────────────────────────────────

def _to_lc_messages(history: list[ChatMessage]) -> list[BaseMessage]:
    lc: list[BaseMessage] = []
    for m in history:
        if m.role == "user":
            lc.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            if m.tool_calls:
                lc.append(AIMessage(content=m.content or "", tool_calls=m.tool_calls))
            else:
                lc.append(AIMessage(content=m.content or ""))
        elif m.role == "tool":
            lc.append(ToolMessage(content=m.content, tool_call_id=m.tool_call_id or ""))
    return lc


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return "<unserializable>"


def _truncate(s: str) -> str:
    if len(s) <= MAX_TOOL_OUTPUT_CHARS:
        return s
    head = MAX_TOOL_OUTPUT_CHARS // 2
    return f"{s[:head]}\n…[truncated]…\n{s[-(MAX_TOOL_OUTPUT_CHARS - head):]}"


# ── Agent loop ────────────────────────────────────────────────────────────────

async def run_chat_turn(  # noqa: C901
    conversation_id: str, user_text: str
) -> AsyncIterator[dict[str, Any]]:
    """Run one user turn, yielding SSE events as an async generator."""

    conversation = memory_state.get_conversation(conversation_id)
    if conversation is None:
        yield {"type": "error", "message": f"Conversation {conversation_id!r} not found."}
        return

    memory_state.append_message(conversation_id, "user", user_text)

    try:
        llm = _chat_model()
    except Exception as err:
        yield {"type": "error", "message": str(err)}
        return

    tools: list[BaseTool] = make_tools(conversation_id)
    tool_by_name: dict[str, BaseTool] = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(list(tools))

    history = memory_state.get_messages(conversation_id, limit=MAX_HISTORY_MESSAGES)
    system = _build_system_prompt(conversation)
    messages: list[BaseMessage] = [SystemMessage(system), *_to_lc_messages(history)]

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info("[chat_agent] iter %d, %d messages", iteration, len(messages))
        accumulated: AIMessageChunk | None = None

        try:
            async for chunk in llm_with_tools.astream(messages):
                if not isinstance(chunk, AIMessageChunk):
                    chunk = AIMessageChunk(content=getattr(chunk, "content", "") or "")
                accumulated = chunk if accumulated is None else accumulated + chunk
                delta = chunk.content if isinstance(chunk.content, str) else ""
                if delta:
                    yield {"type": "text_delta", "content": delta}
        except Exception as err:
            msg = str(err)
            # Gemini thinking models incompatible with DSS's LangChain wrapper
            if "thought_signature" in msg:
                msg = (
                    "The selected LLM is a Gemini thinking model. "
                    "DSS's LangChain wrapper does not yet support thought signatures on tool turns. "
                    "Pick a non-thinking model in Settings."
                )
            logger.exception("[chat_agent] LLM stream failed")
            yield {"type": "error", "message": msg}
            return

        if accumulated is None:
            yield {"type": "error", "message": "LLM returned no chunks."}
            return

        # Normalise tool call IDs — some LLMs reuse the tool name as the id,
        # which collides across iterations.
        normalized_tcs: list[dict] = []
        for tc in (accumulated.tool_calls or []):
            new_tc = dict(tc)
            new_tc["id"] = f"call_{uuid.uuid4().hex[:12]}"
            normalized_tcs.append(new_tc)

        ai_msg = AIMessage(
            content=accumulated.content if isinstance(accumulated.content, str) else "",
            tool_calls=normalized_tcs,
        )
        messages.append(ai_msg)
        memory_state.append_message(
            conversation_id, "assistant", ai_msg.content,
            tool_calls=[dict(tc) for tc in ai_msg.tool_calls],
        )

        if not ai_msg.tool_calls:
            last_msg_id = memory_state.get_messages(conversation_id)[-1].id
            yield {"type": "turn_completed", "message_id": last_msg_id}
            return

        # ── Phase 1: resolve permissions serially ──────────────────────────
        runnable: list[tuple[dict, str, dict, str]] = []
        perm_results: dict[str, tuple[str, bool]] = {}

        for tc in ai_msg.tool_calls:
            name = tc.get("name", "") or ""
            args = tc.get("args") or {}
            call_id = tc.get("id") or name

            decision = settings_service.decide(name)
            if decision == "prompt":
                fut = pb.broker.create_pending(conversation_id, call_id)
                yield {"type": "permission_requested", "id": call_id, "name": name, "args": args}
                try:
                    result = await fut
                except asyncio.CancelledError:
                    output = "Permission request cancelled (connection closed)."
                    yield {"type": "tool_call_started", "id": call_id, "name": name, "args": args}
                    yield {"type": "tool_call_completed", "id": call_id, "name": name, "args": args, "output": output, "ok": False}
                    messages.append(ToolMessage(content=output, tool_call_id=call_id))
                    memory_state.append_message(conversation_id, "tool", output, tool_call_id=call_id)
                    yield {"type": "error", "message": "Stream closed before permission was resolved."}
                    return
                yield {"type": "permission_resolved", "id": call_id, "decision": result.decision, "remember": result.remember}
                if result.decision == "deny":
                    output = "Tool call denied by user."
                    yield {"type": "tool_call_started", "id": call_id, "name": name, "args": args}
                    yield {"type": "tool_call_completed", "id": call_id, "name": name, "args": args, "output": output, "ok": False}
                    perm_results[call_id] = (output, False)
                    continue
                if result.remember:
                    settings_service.set_tool_permission(name, "allow")
                runnable.append((tc, name, args, call_id))
            else:
                runnable.append((tc, name, args, call_id))

        # ── Phase 2: run approved calls concurrently ───────────────────────
        event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
        run_results: dict[str, tuple[str, bool]] = {}

        async def _run_one(name: str, args: dict, call_id: str) -> None:
            await event_queue.put({"type": "tool_call_started", "id": call_id, "name": name, "args": args})
            tool_obj = tool_by_name.get(name)
            if tool_obj is None:
                output, ok = f"Unknown tool: {name}", False
            else:
                try:
                    raw = await tool_obj.ainvoke(args)
                    output, ok = _stringify(raw), True
                except Exception as err:
                    logger.exception("[chat_agent] tool %s raised", name)
                    output, ok = f"Tool raised: {err}", False
            await event_queue.put({"type": "tool_call_completed", "id": call_id, "name": name, "args": args, "output": output, "ok": ok})
            run_results[call_id] = (output, ok)

        async def _run_all() -> None:
            try:
                await asyncio.gather(
                    *(_run_one(n, a, c) for _, n, a, c in runnable),
                    return_exceptions=True,
                )
            finally:
                await event_queue.put(None)

        runner_task = asyncio.create_task(_run_all())
        try:
            while True:
                evt = await event_queue.get()
                if evt is None:
                    break
                yield evt
        except BaseException:
            runner_task.cancel()
            raise
        await runner_task

        # ── Phase 3: append ToolMessages in canonical order ────────────────
        for tc in ai_msg.tool_calls:
            call_id = tc.get("id") or (tc.get("name", "") or "")
            if call_id in run_results:
                output, _ = run_results[call_id]
            elif call_id in perm_results:
                continue  # ToolMessage already appended inline above
            else:
                continue
            messages.append(ToolMessage(content=_truncate(output), tool_call_id=call_id))
            memory_state.append_message(conversation_id, "tool", output, tool_call_id=call_id)

    yield {"type": "error", "message": f"Agent reached max_iterations={MAX_ITERATIONS} without finishing."}

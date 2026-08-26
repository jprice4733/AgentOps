import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiUrl } from '@/utils/api'
import type { Conversation, ChatMessageData, UiMessage, UiToolCall } from '@/types/chat'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<UiMessage[]>([])
  const streaming = ref(false)
  const error = ref<string | null>(null)

  // ── Conversations ────────────────────────────────────────────────────────

  async function loadConversations(): Promise<void> {
    const res = await fetch(apiUrl('/api/chat/conversations'))
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    conversations.value = (await res.json()) as Conversation[]
  }

  async function selectConversation(id: string): Promise<void> {
    activeConversationId.value = id
    const res = await fetch(apiUrl(`/api/chat/conversations/${id}/messages`))
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const raw = (await res.json()) as ChatMessageData[]
    messages.value = hydrateMessages(raw)
  }

  async function createConversation(): Promise<Conversation> {
    const res = await fetch(apiUrl('/api/chat/conversations'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'New conversation' }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const conv = (await res.json()) as Conversation
    conversations.value = [conv, ...conversations.value]
    activeConversationId.value = conv.id
    messages.value = []
    return conv
  }

  async function deleteConversation(id: string): Promise<void> {
    await fetch(apiUrl(`/api/chat/conversations/${id}`), { method: 'DELETE' })
    conversations.value = conversations.value.filter((c) => c.id !== id)
    if (activeConversationId.value === id) {
      activeConversationId.value = null
      messages.value = []
    }
  }

  // ── Streaming ────────────────────────────────────────────────────────────

  let _localSeq = 0

  /** Append a streaming assistant placeholder. Returns its index. */
  function _startAssistantMessage(): number {
    _localSeq += 1
    messages.value.push({ id: `streaming-${Date.now()}-${_localSeq}`, role: 'assistant', content: '', toolCalls: [], streaming: true })
    return messages.value.length - 1
  }

  /** Apply one SSE event to the active assistant message; returns the (possibly
   *  advanced) active index. */
  function applyEvent(event: { type: string; [k: string]: unknown }, activeIdx: number): number {
    let idx = activeIdx
    let msg = messages.value[idx]
    if (!msg) return idx

    if (event.type === 'text_delta') {
      // The model streams text in two places: commentary *before* it calls tools,
      // and its answer *after* the tool results come back. When the active message
      // already issued tool calls and they've all settled, this delta is that
      // later step — start a fresh assistant bubble so the answer renders BELOW
      // the tool cards. This matches the order a reloaded conversation shows (the
      // backend persists one assistant message per LLM step). Without the split,
      // a turn's pre- and post-tool text collapse into one bubble above the tools.
      if (msg.toolCalls.length > 0 && msg.toolCalls.every((t) => t.output !== undefined)) {
        msg.streaming = false
        idx = _startAssistantMessage()
        msg = messages.value[idx]
      }
      msg.content += (event.content as string) ?? ''
    } else if (event.type === 'tool_call_started') {
      msg.toolCalls.push({
        id: event.id as string,
        name: event.name as string,
        args: (event.args as Record<string, unknown>) ?? {},
      })
    } else if (event.type === 'tool_call_completed') {
      const tc = msg.toolCalls.find((t) => t.id === event.id)
      if (tc) {
        tc.output = event.output as string
        tc.ok = event.ok as boolean
        tc.pendingPermission = false
      }
    } else if (event.type === 'permission_requested') {
      const tc = msg.toolCalls.find((t) => t.id === event.id)
      if (tc) tc.pendingPermission = true
    } else if (event.type === 'permission_resolved') {
      const tc = msg.toolCalls.find((t) => t.id === event.id)
      if (tc) {
        tc.pendingPermission = false
        tc.decision = event.decision as 'allow' | 'deny'
      }
    } else if (event.type === 'turn_completed') {
      msg.id = (event.message_id as string) ?? msg.id
      msg.streaming = false
    } else if (event.type === 'error') {
      msg.content += `\n\n*Error: ${event.message}*`
      msg.streaming = false
    }
    return idx
  }

  /** Send a message and consume the SSE stream. */
  async function send(
    text: string,
    onPermissionNeeded: (callId: string, name: string, args: Record<string, unknown>) => void,
  ): Promise<void> {
    streaming.value = true
    error.value = null

    // Optimistically add user message.
    messages.value.push({ id: `user-${Date.now()}`, role: 'user', content: text, toolCalls: [] })
    let activeIdx = _startAssistantMessage()

    try {
      const res = await fetch(apiUrl('/api/chat/messages'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ conversationId: activeConversationId.value, text }),
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      const watchdog = setTimeout(() => reader.cancel(), 90_000)

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
          const parts = buf.split('\n\n')
          buf = parts.pop() ?? ''
          for (const part of parts) {
            const dataLine = part.split('\n').find((l) => l.startsWith('data:'))
            if (!dataLine) continue
            const raw = dataLine.slice(5).trim()
            if (!raw || raw === '[DONE]') continue
            const evt = JSON.parse(raw) as { type: string; [k: string]: unknown }
            if (evt.type === 'conversation') {
              activeConversationId.value = evt.conversation_id as string
              await loadConversations().catch(() => {})
            } else if (evt.type === 'permission_requested') {
              onPermissionNeeded(evt.id as string, evt.name as string, (evt.args as Record<string, unknown>) ?? {})
            }
            activeIdx = applyEvent(evt, activeIdx)
          }
        }
      } finally {
        clearTimeout(watchdog)
      }
    } catch (e) {
      const msg = messages.value[activeIdx]
      if (msg) { msg.content += '\n\n*Stream error*'; msg.streaming = false }
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      streaming.value = false
    }
  }

  /** Resolve a tool permission prompt. */
  async function resolvePermission(
    callId: string,
    decision: 'allow' | 'deny',
    remember: boolean,
  ): Promise<void> {
    const convId = activeConversationId.value
    if (!convId) return
    await fetch(apiUrl(`/api/chat/permissions/${convId}/${callId}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, remember }),
    })
  }

  return {
    conversations,
    activeConversationId,
    messages,
    streaming,
    error,
    loadConversations,
    selectConversation,
    createConversation,
    deleteConversation,
    send,
    resolvePermission,
  }
})

// ── History hydration ─────────────────────────────────────────────────────────

function hydrateMessages(raw: ChatMessageData[]): UiMessage[] {
  const out: UiMessage[] = []
  const toolResults = new Map<string, string>()

  // First pass: collect tool outputs.
  for (const m of raw) {
    if (m.role === 'tool' && m.tool_call_id) {
      toolResults.set(m.tool_call_id, m.content)
    }
  }

  // Second pass: build UI messages.
  for (const m of raw) {
    if (m.role === 'tool') continue  // merged into assistant
    const toolCalls: UiToolCall[] = (m.tool_calls ?? []).map((tc) => ({
      id: tc.id,
      name: tc.name,
      args: tc.args ?? {},
      output: toolResults.get(tc.id),
      ok: toolResults.has(tc.id),
    }))
    out.push({ id: m.id, role: m.role as 'user' | 'assistant', content: m.content, toolCalls })
  }
  return out
}

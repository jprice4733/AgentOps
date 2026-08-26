export interface Conversation {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export interface ToolCall {
  id: string
  name: string
  args: Record<string, unknown>
}

export interface ChatMessageData {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_calls: ToolCall[]
  tool_call_id: string | null
  created_at: string
}

/** A UI-side message model (richer than the wire format). */
export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls: UiToolCall[]
  streaming?: boolean
}

export interface UiToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  output?: string
  ok?: boolean
  /** Permission approval required. */
  pendingPermission?: boolean
  decision?: 'allow' | 'deny'
}

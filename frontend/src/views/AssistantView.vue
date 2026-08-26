<script setup lang="ts">
/**
 * AssistantView — chatbot UI for the Chatbot building block.
 *
 * Enabled when ENABLE_CHATBOT=1 in app.env.
 * Conversations and messages are persisted in SQLite.
 * The agent runs on the backend via DSS LLM Mesh + langchain-core.
 *
 * Key patterns:
 *  - SSE consumed via fetch+manual reader (not EventSource — sidesteps
 *    iframe/cross-origin limits). See stores/chat.ts useChatStream composable.
 *  - Tool-call approval: the backend suspends the agent loop and emits
 *    permission_requested; the user approves/denies inline via ToolCallCard.
 *  - apiUrl() for all fetches — see README "non-obvious bits".
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  MessageSquare, SquarePen,
  Send, Loader2, Trash2,
  ChevronLeft, ChevronRight,
} from 'lucide-vue-next'
import { EaEmpty } from '@/components/ui'
import { useChatStore } from '@/stores/chat'
import ChatMessage from '@/components/chat/ChatMessage.vue'

defineOptions({ name: 'AssistantView' })

const store = useChatStore()

// ── Composition ────────────────────────────────────────────────────────────────
const inputText = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const historyOpen = ref(true)

// Pending permission prompts surfaced to the top for the allow/deny buttons.
const pendingPermissions = ref<Array<{ callId: string; name: string; args: Record<string, unknown> }>>([])

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

onMounted(async () => {
  await store.loadConversations().catch(() => {})
  if (store.conversations.length) {
    await store.selectConversation(store.conversations[0].id)
    scrollToBottom()
  }
})

// ── Relative time ──────────────────────────────────────────────────────────────
function relativeTime(iso: string | undefined): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const s = Math.round(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.round(h / 24)
  return `${d}d ago`
}

// ── Send ───────────────────────────────────────────────────────────────────────
async function send() {
  const text = inputText.value.trim()
  if (!text || store.streaming) return
  inputText.value = ''
  pendingPermissions.value = []

  if (!store.activeConversationId) {
    await store.createConversation()
  }

  await store.send(text, (callId, name, args) => {
    pendingPermissions.value.push({ callId, name, args })
    scrollToBottom()
  })
  scrollToBottom()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

// ── Permission ─────────────────────────────────────────────────────────────────
async function resolvePermission(callId: string, decision: 'allow' | 'deny', remember: boolean) {
  pendingPermissions.value = pendingPermissions.value.filter((p) => p.callId !== callId)
  await store.resolvePermission(callId, decision, remember)
}

// ── Conversations ──────────────────────────────────────────────────────────────
async function newConversation() {
  await store.createConversation()
  messagesEl.value && scrollToBottom()
}

async function selectConversation(id: string) {
  if (id === store.activeConversationId) return
  pendingPermissions.value = []
  await store.selectConversation(id)
  scrollToBottom()
}

async function deleteConversation(id: string) {
  await store.deleteConversation(id)
  // If there are remaining conversations, select the first one.
  if (store.conversations.length) {
    await store.selectConversation(store.conversations[0].id)
    scrollToBottom()
  }
}

const activeConversation = computed(() =>
  store.activeConversationId
    ? store.conversations.find((c) => c.id === store.activeConversationId)
    : undefined,
)

const sortedConversations = computed(() =>
  [...store.conversations].sort((a, b) =>
    (b.updated_at ?? '').localeCompare(a.updated_at ?? ''),
  ),
)

const hasMessages = computed(() => store.messages.length > 0)
</script>

<template>
  <div
    class="h-full w-full grid gap-0 min-h-0 min-w-0 transition-[grid-template-columns] duration-200"
    :style="historyOpen
      ? 'grid-template-columns: 256px minmax(0,1fr)'
      : 'grid-template-columns: 40px minmax(0,1fr)'"
  >

    <!-- History rail -->
    <aside class="flex flex-col bg-muted/10 overflow-hidden min-w-0" :class="historyOpen ? 'border-r' : ''">
      <header class="h-16 border-b px-3 flex items-center gap-2 shrink-0">
        <template v-if="historyOpen">
          <span class="text-sm font-medium truncate">Conversations</span>
          <span class="text-[11px] text-muted-foreground">{{ store.conversations.length }}</span>
        </template>
      </header>

      <template v-if="historyOpen">
        <div class="flex-1 overflow-auto px-2 pt-2 pb-3 space-y-1 min-w-0">
          <div
            v-if="!sortedConversations.length"
            class="text-xs text-muted-foreground italic px-1 py-2 text-center"
          >
            No conversations yet.
          </div>
          <div
            v-for="conv in sortedConversations"
            :key="conv.id"
            class="group relative w-full rounded-md min-w-0"
            :class="conv.id === store.activeConversationId
              ? 'bg-accent text-foreground'
              : 'text-foreground/90 hover:bg-accent/60'"
          >
            <button
              type="button"
              class="w-full text-left px-2.5 py-2 flex flex-col gap-0.5 min-w-0 pr-7"
              @click="selectConversation(conv.id)"
            >
              <div class="flex items-center gap-1.5 min-w-0">
                <MessageSquare class="w-3 h-3 text-muted-foreground shrink-0" />
                <span class="text-xs font-medium truncate">{{ conv.name || '(untitled)' }}</span>
              </div>
              <div class="text-[10px] text-muted-foreground pl-4">
                {{ relativeTime(conv.updated_at) }}
              </div>
            </button>
            <button
              type="button"
              class="absolute right-1.5 top-1.5 p-1 rounded opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
              title="Delete conversation"
              @click.stop="deleteConversation(conv.id)"
            >
              <Trash2 class="w-3 h-3" />
            </button>
          </div>
        </div>
      </template>
    </aside>

    <!-- Chat column -->
    <div class="flex flex-col min-w-0 min-h-0">
      <header class="h-16 border-b px-4 flex items-center gap-2 shrink-0 min-w-0">
        <button
          type="button"
          class="text-muted-foreground hover:text-foreground transition-colors shrink-0"
          :title="historyOpen ? 'Collapse history' : 'Expand history'"
          @click="historyOpen = !historyOpen"
        >
          <ChevronLeft v-if="historyOpen" class="w-4 h-4" />
          <ChevronRight v-else class="w-4 h-4" />
        </button>
        <span class="text-sm font-medium truncate">
          {{ activeConversation?.name ?? 'New conversation' }}
        </span>
        <button
          type="button"
          class="ml-auto text-muted-foreground hover:text-foreground transition-colors shrink-0"
          title="New conversation"
          @click="newConversation"
        >
          <SquarePen class="w-4 h-4" />
        </button>
      </header>

      <!-- Messages -->
      <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-4 min-h-0">
        <EaEmpty
          v-if="!hasMessages"
          :icon="MessageSquare"
          title="Start a conversation"
          description="Ask a question or issue a command. Pick an LLM in Settings first — the agent can then list datasets and call tools with your approval."
        />

        <div class="mx-auto w-full max-w-3xl space-y-4">
          <ChatMessage
            v-for="msg in store.messages"
            :key="msg.id"
            :message="msg"
            @resolve-permission="(callId, decision, remember) => resolvePermission(callId, decision, remember)"
          />
        </div>
      </div>

      <!-- Input area -->
      <form class="border-t bg-background p-3" @submit.prevent="send">
        <div class="mx-auto w-full max-w-3xl flex items-end gap-2 min-w-0">
          <textarea
            v-model="inputText"
            rows="1"
            placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
            class="flex-1 min-w-0 resize-none rounded-md border bg-background px-3 py-2 text-sm
                   placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 max-h-40"
            :disabled="store.streaming"
            @keydown="onKeydown"
          />
          <button
            type="submit"
            class="inline-flex items-center justify-center rounded-md bg-primary text-primary-foreground
                   w-9 h-9 disabled:opacity-50 shrink-0 transition-colors hover:bg-primary/90"
            :disabled="!inputText.trim() || store.streaming"
          >
            <Loader2 v-if="store.streaming" class="w-4 h-4 animate-spin" />
            <Send v-else class="w-4 h-4" />
          </button>
        </div>
        <p v-if="store.error" class="mx-auto w-full max-w-3xl text-xs text-destructive mt-1">{{ store.error }}</p>
      </form>
    </div>

  </div>
</template>

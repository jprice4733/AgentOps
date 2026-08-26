<script setup lang="ts">
/**
 * ToolCallCard — displays a single agent tool call with its outcome.
 *
 * When ``pendingPermission`` is true the card shows Allow/Deny buttons.
 * This is the entire UI surface for the tool-call approval flow:
 *   1. Backend emits ``permission_requested`` → card shows approval buttons.
 *   2. User clicks Allow or Deny (+ optional "remember").
 *   3. Parent calls resolvePermission → POST /api/chat/permissions/{conv}/{call}.
 *   4. Backend resolves the asyncio.Future and resumes the agent loop.
 *
 * **What this is NOT:** this is not access-control — it does not gate who can
 * use the chatbot. It gates what the agent is allowed to DO on behalf of the
 * user who is already authenticated to DSS.
 */
import { ref } from 'vue'
import { ChevronDown, ChevronUp, CheckCircle2, XCircle, Loader2, Wrench } from 'lucide-vue-next'
import type { UiToolCall } from '@/types/chat'

defineOptions({ name: 'ToolCallCard' })

defineProps<{ toolCall: UiToolCall }>()
const emit = defineEmits<{
  resolvePermission: [decision: 'allow' | 'deny', remember: boolean]
}>()

const expanded = ref(false)
const remember = ref(false)
</script>

<template>
  <div class="rounded-lg border text-xs overflow-hidden">
    <!-- Header row -->
    <div
      class="flex items-center gap-2 px-3 py-2 bg-muted/20 cursor-pointer select-none"
      @click="expanded = !expanded"
    >
      <Loader2
        v-if="!toolCall.output && !toolCall.pendingPermission"
        class="w-3.5 h-3.5 animate-spin text-muted-foreground shrink-0"
      />
      <CheckCircle2
        v-else-if="toolCall.ok"
        class="w-3.5 h-3.5 text-green-500 shrink-0"
      />
      <XCircle
        v-else-if="toolCall.output && !toolCall.ok"
        class="w-3.5 h-3.5 text-destructive shrink-0"
      />
      <Wrench
        v-else
        class="w-3.5 h-3.5 text-muted-foreground shrink-0"
      />

      <span class="font-mono font-medium text-foreground">{{ toolCall.name }}</span>
      <span v-if="toolCall.pendingPermission" class="ml-1 text-muted-foreground italic">
        — awaiting approval
      </span>
      <span class="ml-auto">
        <ChevronDown v-if="!expanded" class="w-3.5 h-3.5 text-muted-foreground" />
        <ChevronUp v-else class="w-3.5 h-3.5 text-muted-foreground" />
      </span>
    </div>

    <!-- Expanded: args + output -->
    <div v-if="expanded" class="px-3 py-2 space-y-2 border-t bg-muted/10">
      <div v-if="Object.keys(toolCall.args).length">
        <p class="font-semibold text-muted-foreground mb-0.5">Arguments</p>
        <pre class="font-mono text-xs overflow-x-auto whitespace-pre-wrap break-all">{{ JSON.stringify(toolCall.args, null, 2) }}</pre>
      </div>
      <div v-if="toolCall.output">
        <p class="font-semibold text-muted-foreground mb-0.5">Output</p>
        <pre class="font-mono text-xs overflow-x-auto whitespace-pre-wrap break-all max-h-40">{{ toolCall.output }}</pre>
      </div>
    </div>

    <!-- Permission approval row -->
    <div
      v-if="toolCall.pendingPermission"
      class="px-3 py-2 border-t bg-muted/5 flex items-center gap-3"
    >
      <label class="flex items-center gap-1.5 text-muted-foreground cursor-pointer">
        <input v-model="remember" type="checkbox" class="rounded" />
        Remember choice
      </label>
      <div class="ml-auto flex gap-2">
        <button
          class="px-3 py-1 rounded bg-destructive/10 text-destructive text-xs font-medium hover:bg-destructive/20 transition-colors"
          @click.stop="emit('resolvePermission', 'deny', remember)"
        >
          Deny
        </button>
        <button
          class="px-3 py-1 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
          @click.stop="emit('resolvePermission', 'allow', remember)"
        >
          Allow
        </button>
      </div>
    </div>
  </div>
</template>

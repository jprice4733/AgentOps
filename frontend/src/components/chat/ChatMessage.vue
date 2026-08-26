<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import { User, Bot } from 'lucide-vue-next'
import type { UiMessage } from '@/types/chat'
import ToolCallCard from './ToolCallCard.vue'

defineOptions({ name: 'ChatMessage' })

const props = defineProps<{ message: UiMessage }>()
const emit = defineEmits<{
  resolvePermission: [callId: string, decision: 'allow' | 'deny', remember: boolean]
}>()

const html = computed(() => {
  if (!props.message.content) return ''
  return marked.parse(props.message.content) as string
})

const hasContent = computed(() =>
  Boolean(html.value) || Boolean(props.message.toolCalls?.length),
)
</script>

<template>
  <!-- User message -->
  <div v-if="message.role === 'user'" class="flex gap-2.5 justify-end min-w-0">
    <div class="max-w-[85%] min-w-0 rounded-lg bg-primary text-primary-foreground px-3 py-2 text-sm whitespace-pre-wrap break-words">
      {{ message.content }}
    </div>
    <div class="w-7 h-7 rounded-full bg-muted flex items-center justify-center shrink-0 text-muted-foreground">
      <User class="w-4 h-4" />
    </div>
  </div>

  <!-- Assistant message -->
  <template v-else>
    <div v-if="hasContent" class="flex gap-2.5 min-w-0">
      <div class="w-7 h-7 rounded-full bg-indigo-50 flex items-center justify-center shrink-0 text-indigo-600">
        <Bot class="w-4 h-4" />
      </div>
      <div class="flex-1 min-w-0 space-y-1">
        <div
          v-if="html"
          class="chat-markdown text-sm prose prose-sm max-w-none prose-table:text-sm prose-pre:my-1 prose-pre:text-xs prose-code:text-xs"
          v-html="html"
        />
        <div v-if="message.toolCalls && message.toolCalls.length">
          <ToolCallCard
            v-for="tc in message.toolCalls"
            :key="tc.id"
            :tool-call="tc"
            @resolve-permission="(decision, remember) => emit('resolvePermission', tc.id, decision, remember)"
          />
        </div>
      </div>
    </div>

    <!-- Thinking indicator while streaming with no content yet -->
    <div v-if="message.streaming && !message.content" class="flex gap-2.5 min-w-0 items-center">
      <div class="w-7 h-7 rounded-full bg-indigo-50 flex items-center justify-center shrink-0 text-indigo-600">
        <Bot class="w-4 h-4" />
      </div>
      <div class="flex items-center gap-1 text-indigo-400">
        <span class="thinking-dot" />
        <span class="thinking-dot" />
        <span class="thinking-dot" />
      </div>
    </div>
  </template>
</template>

<style scoped>
.chat-markdown :deep(pre) {
  overflow-x: auto;
  max-width: 100%;
}
.chat-markdown :deep(table) {
  display: block;
  overflow-x: auto;
  max-width: 100%;
}
.chat-markdown :deep(code) {
  word-break: break-word;
  overflow-wrap: anywhere;
}

.thinking-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: currentColor;
  animation: thinking-bounce 1.2s ease-in-out infinite;
}
.thinking-dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes thinking-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
  30% { transform: translateY(-4px); opacity: 1; }
}
</style>

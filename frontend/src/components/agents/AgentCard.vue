<script setup lang="ts">
/**
 * AgentCard — copy-this template for card grids.
 *
 * One entity per card: icon + title row, status pill, description, and a
 * metadata footer. Design tokens only (bg-card, text-muted-foreground, …);
 * status pills use Tailwind's emerald/rose scales for semantic color.
 */
import { Bot, Activity, Clock } from 'lucide-vue-next'
import type { Agent } from '@/types/agents'

defineOptions({ name: 'AgentCard' })

defineProps<{ agent: Agent }>()

const statusClass: Record<Agent['status'], string> = {
  active: 'bg-emerald-50 text-emerald-700',
  paused: 'bg-muted text-muted-foreground',
  error: 'bg-rose-50 text-rose-700',
}
</script>

<template>
  <div class="rounded-xl border bg-card p-5 flex flex-col gap-3">
    <div class="flex items-start justify-between gap-3">
      <div class="flex items-center gap-2 min-w-0">
        <Bot class="w-4 h-4 text-muted-foreground shrink-0" />
        <p class="text-sm font-semibold truncate">{{ agent.name }}</p>
      </div>
      <span
        class="px-1.5 py-0.5 rounded-md text-[11px] font-medium shrink-0 capitalize"
        :class="statusClass[agent.status]"
      >
        {{ agent.status }}
      </span>
    </div>

    <p class="text-xs text-muted-foreground leading-snug flex-1">{{ agent.description }}</p>

    <div class="flex items-center gap-4 text-xs text-muted-foreground border-t pt-3">
      <span class="font-mono">{{ agent.model }}</span>
      <span class="inline-flex items-center gap-1">
        <Activity class="w-3 h-3" />
        {{ agent.runs_today }} runs
      </span>
      <span class="inline-flex items-center gap-1 ml-auto">
        <Clock class="w-3 h-3" />
        {{ agent.last_run }}
      </span>
    </div>
  </div>
</template>

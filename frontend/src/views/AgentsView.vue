<script setup lang="ts">
/**
 * AgentsView — card-grid demo for the Administration section.
 *
 * Renders a responsive grid of AgentCard components fetched from the backend.
 * To make it real, replace GET /api/agents/sample with your domain entities
 * (DSS agents, scheduled jobs, monitored pipelines, …).
 *
 * Always built in — visibility is controlled at runtime by the Admin sidebar
 * toggle (stores/admin.ts), not an ENABLE_* flag.
 */
import { onMounted } from 'vue'
import { Bot } from 'lucide-vue-next'
import { EaEmpty } from '@/components/ui'
import { useAgentsStore } from '@/stores/agents'
import AgentCard from '@/components/agents/AgentCard.vue'

defineOptions({ name: 'AgentsView' })

const store = useAgentsStore()
onMounted(() => store.loadAgents())
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="shrink-0 h-16 border-b px-8 flex flex-col justify-center">
      <h1 class="text-xl font-semibold tracking-tight">Agents</h1>
      <p class="text-sm text-muted-foreground mt-0.5">A card-grid blueprint backed by a sample route.</p>
    </header>
    <div class="flex-1 overflow-auto">
    <div class="max-w-5xl mx-auto p-8 space-y-6">

      <!-- Loading -->
      <div v-if="store.loading" class="flex items-center justify-center py-16">
        <div class="w-8 h-8 rounded-full bg-muted animate-pulse" />
      </div>

      <!-- Error -->
      <div v-else-if="store.error" class="flex items-center justify-center py-16">
        <EaEmpty :icon="Bot" title="Could not load agents" :description="store.error" />
      </div>

      <!-- Empty -->
      <div v-else-if="!store.agents.length" class="flex items-center justify-center py-16">
        <EaEmpty :icon="Bot" title="No agents" description="The backend returned an empty list." />
      </div>

      <!-- Card grid -->
      <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <AgentCard v-for="agent in store.agents" :key="agent.id" :agent="agent" />
      </div>
    </div>
    </div>
  </div>
</template>

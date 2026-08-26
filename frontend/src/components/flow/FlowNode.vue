<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { Database, Cpu, Sparkles, CheckCircle2, Box } from 'lucide-vue-next'

interface FlowNodeData {
  label: string
  nodeType: string
}

defineProps<{
  id: string
  data: FlowNodeData
}>()

// Each pipeline stage gets a distinct icon + color so nodes are visually
// distinguishable at a glance. Palette follows the same Tailwind design-token
// pattern used in the dashboard components.
const PALETTE: Record<string, { bg: string; fg: string; icon: unknown }> = {
  source:    { bg: 'bg-teal-50',    fg: 'text-teal-600',    icon: Database },
  transform: { bg: 'bg-indigo-50',  fg: 'text-indigo-600',  icon: Cpu },
  enrich:    { bg: 'bg-amber-50',   fg: 'text-amber-600',   icon: Sparkles },
  output:    { bg: 'bg-emerald-50', fg: 'text-emerald-600', icon: CheckCircle2 },
}
const DEFAULT_PALETTE = { bg: 'bg-muted', fg: 'text-muted-foreground', icon: Box }
</script>

<template>
  <div class="rounded-lg border border-stone-200 bg-white shadow-sm px-4 py-3 w-[160px] hover:shadow-md transition-shadow duration-200">
    <Handle type="target" :position="Position.Left" class="flow-handle" />

    <div class="flex items-center gap-2.5">
      <div
        class="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
        :class="(PALETTE[data.nodeType] ?? DEFAULT_PALETTE).bg"
      >
        <component
          :is="(PALETTE[data.nodeType] ?? DEFAULT_PALETTE).icon"
          class="w-4 h-4"
          :class="(PALETTE[data.nodeType] ?? DEFAULT_PALETTE).fg"
        />
      </div>
      <span class="text-[13px] font-semibold text-foreground leading-tight">
        {{ data.label }}
      </span>
    </div>

    <Handle type="source" :position="Position.Right" class="flow-handle" />
  </div>
</template>

<style scoped>
/* Handles are invisible — they exist only as edge-anchor points. */
:deep(.flow-handle) {
  width: 6px !important;
  height: 6px !important;
  background: transparent !important;
  border: none !important;
  opacity: 0;
}
</style>

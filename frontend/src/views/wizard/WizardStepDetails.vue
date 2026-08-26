<script setup lang="ts">
import { useWizardStore } from '@/stores/wizard'

defineOptions({ name: 'WizardStepDetails' })

const store = useWizardStore()
</script>

<template>
  <div class="space-y-4">
    <div class="space-y-1.5">
      <label class="text-sm">
        Notes
        <span class="text-muted-foreground font-normal">(optional)</span>
      </label>
      <textarea
        v-model="store.notes"
        rows="6"
        placeholder="Describe the goal, expected output, or any context…"
        maxlength="2000"
        class="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm
               placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <p class="text-xs text-muted-foreground text-right tabular-nums">
        {{ store.notes.length }}/2000
      </p>
    </div>
  </div>
</template>

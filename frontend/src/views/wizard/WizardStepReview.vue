<script setup lang="ts">
import { useWizardStore } from '@/stores/wizard'

defineOptions({ name: 'WizardStepReview' })

const store = useWizardStore()
</script>

<template>
  <div class="space-y-3">
    <p class="text-sm text-muted-foreground">Review your entries before creating:</p>
    <dl class="space-y-2 text-sm">
      <div class="grid grid-cols-[6rem_1fr] gap-2">
        <dt class="font-medium text-muted-foreground">Name</dt>
        <dd>{{ store.name }}</dd>
      </div>
      <div class="grid grid-cols-[6rem_1fr] gap-2">
        <dt class="font-medium text-muted-foreground">Category</dt>
        <dd>{{ store.category }}</dd>
      </div>
      <div v-if="store.notes" class="grid grid-cols-[6rem_1fr] gap-2">
        <dt class="font-medium text-muted-foreground">Notes</dt>
        <dd class="whitespace-pre-wrap">{{ store.notes }}</dd>
      </div>
    </dl>
  </div>
</template>

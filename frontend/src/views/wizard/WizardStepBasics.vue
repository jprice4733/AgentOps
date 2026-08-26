<script setup lang="ts">
import { EaSelect } from '@/components/ui'
import { useWizardStore } from '@/stores/wizard'

defineOptions({ name: 'WizardStepBasics' })

const store = useWizardStore()

const CATEGORIES = ['Analysis', 'Report', 'Pipeline', 'Experiment', 'Other']
</script>

<template>
  <div class="space-y-4">
    <div class="space-y-1.5">
      <label class="text-sm">
        Name <span class="text-destructive" aria-hidden="true">*</span>
      </label>
      <input
        v-model="store.name"
        type="text"
        placeholder="e.g. Q3 Revenue Analysis"
        maxlength="120"
        class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm
               placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      />
    </div>
    <div class="space-y-1.5">
      <label class="text-sm">
        Category <span class="text-destructive" aria-hidden="true">*</span>
      </label>
      <EaSelect
        :model-value="store.category || undefined"
        :options="CATEGORIES"
        placeholder="Pick a category…"
        @update:model-value="store.category = $event ?? ''"
      />
    </div>
  </div>
</template>

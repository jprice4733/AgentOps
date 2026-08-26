<script setup lang="ts">
  import { computed } from 'vue'
  import { SwitchRoot, SwitchThumb } from 'reka-ui'

  const props = defineProps<{
    id: string
    label: string
    description: string
    modelValue?: boolean
    disabled?: boolean
  }>()

  const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void
  }>()

  const model = computed({
    get: () => props.modelValue ?? false,
    set: (value) => emit('update:modelValue', value),
  })
</script>

<template>
  <div
    class="flex flex-row items-center justify-between rounded-lg border p-4"
    :class="{ 'opacity-60 select-none pointer-events-none': disabled }"
  >
    <div class="space-y-0.5">
      <label :for="id" class="text-base font-medium text-foreground">{{ label }}</label>
      <p class="text-sm text-muted-foreground">{{ description }}</p>
    </div>
    <SwitchRoot
      :id="id"
      v-model="model"
      :disabled="disabled"
      class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent
             transition-colors data-[state=checked]:bg-primary data-[state=unchecked]:bg-input
             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      <SwitchThumb
        class="pointer-events-none block h-4 w-4 rounded-full bg-background shadow-sm transition-transform
               data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0.5"
      />
    </SwitchRoot>
  </div>
</template>

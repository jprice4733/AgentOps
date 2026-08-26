<script setup lang="ts">
  import { computed } from 'vue'
  import {
    SelectRoot,
    SelectTrigger,
    SelectValue,
    SelectIcon,
    SelectPortal,
    SelectContent,
    SelectViewport,
    SelectItem,
    SelectItemText,
    SelectItemIndicator,
  } from 'reka-ui'
  import { Check, ChevronDown } from 'lucide-vue-next'

  // Drop-in for the former truenorth EaSelect: a styled custom dropdown (not a
  // native <select>) built on reka-ui's headless Select. Same props/events.
  defineOptions({ inheritAttrs: false })

  const props = defineProps<{
    modelValue: string | undefined
    options: (string | { value: string; label: string })[]
    placeholder?: string
    disabled?: boolean
  }>()

  const emit = defineEmits<{
    (e: 'update:modelValue', value: string): void
  }>()

  const normalizedOptions = computed(() =>
    props.options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o)),
  )
</script>

<template>
  <SelectRoot
    :model-value="modelValue"
    :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event as string)"
  >
    <!-- $attrs carries the consumer's `class` (e.g. w-72) onto the trigger. -->
    <SelectTrigger
      v-bind="$attrs"
      class="flex h-9 items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-sm transition-colors hover:bg-accent/40 focus:outline-none focus:ring-2 focus:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-60 data-[placeholder]:text-muted-foreground"
    >
      <SelectValue :placeholder="placeholder || 'Select an option'" class="truncate" />
      <SelectIcon as-child>
        <ChevronDown class="h-4 w-4 shrink-0 opacity-60" />
      </SelectIcon>
    </SelectTrigger>

    <SelectPortal>
      <SelectContent
        position="popper"
        :side-offset="4"
        class="z-50 max-h-[18rem] min-w-[var(--reka-select-trigger-width)] overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95"
      >
        <SelectViewport class="p-1">
          <SelectItem
            v-for="option in normalizedOptions"
            :key="option.value"
            :value="option.value"
            class="relative flex cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-3 text-sm text-foreground outline-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground data-[state=checked]:font-medium data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
          >
            <SelectItemIndicator class="absolute left-2 inline-flex items-center">
              <Check class="h-4 w-4" />
            </SelectItemIndicator>
            <SelectItemText>{{ option.label }}</SelectItemText>
          </SelectItem>
        </SelectViewport>
      </SelectContent>
    </SelectPortal>
  </SelectRoot>
</template>

<script setup lang="ts">
  import type { Component } from 'vue'

  defineProps<{
    icon: Component
    title: string
    description?: string
  }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center text-center py-12 px-6">
    <div class="flex items-center justify-center w-12 h-12 rounded-lg bg-muted text-muted-foreground mb-4">
      <component :is="icon" class="w-6 h-6" />
    </div>
    <h3 class="text-sm font-semibold text-foreground">{{ title }}</h3>
    <p v-if="description" class="text-sm text-muted-foreground mt-1 max-w-md">
      {{ description }}
    </p>
    <div class="mt-4">
      <slot />
    </div>
  </div>
</template>

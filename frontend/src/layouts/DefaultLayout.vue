<script setup lang="ts">
import AppSidebar from '@/components/layout/AppSidebar.vue'

defineOptions({ name: 'AppDefaultLayout' })
</script>

<template>
  <div class="h-screen bg-background text-foreground flex">
    <AppSidebar />
    <div class="flex-1 flex flex-col overflow-auto">
      <main class="flex-1 overflow-auto">
        <router-view />
      </main>
    </div>
  </div>
</template>

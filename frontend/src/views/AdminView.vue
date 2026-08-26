<script setup lang="ts">
/**
 * AdminView — runtime toggles for sidebar sections.
 *
 * State lives in stores/admin.ts (localStorage, per-browser). This is a UI
 * preference, not authorization: DSS project permissions control who can use
 * the app. Add real RBAC if hidden sections must be enforced server-side.
 */
import { SettingsSwitchItem } from '@/components/ui'
import { useAdminStore } from '@/stores/admin'

defineOptions({ name: 'AdminView' })

const adminStore = useAdminStore()
</script>

<template>
  <div class="h-full overflow-auto">
    <div class="max-w-3xl mx-auto p-8 space-y-8">
      <header>
        <h1 class="text-2xl font-semibold">Admin</h1>
        <p class="text-sm text-muted-foreground mt-1">
          Control which sidebar sections are visible. Stored in your browser (localStorage).
        </p>
      </header>

      <SettingsSwitchItem
        id="show-administration"
        v-model="adminStore.showAdministration"
        label="Show Administration section"
        description="Display the Administration section (Agents) in the sidebar."
      />
    </div>
  </div>
</template>

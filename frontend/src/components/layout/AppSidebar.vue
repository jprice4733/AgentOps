<script setup lang="ts">
  import { computed } from 'vue'
  import { useRoute, useRouter, RouterLink } from 'vue-router'
  import { MoveLeft, Plus } from 'lucide-vue-next'
  import { storeToRefs } from 'pinia'
  import { APP_NAME, APP_ICON } from '@/config'
  import { useAdminStore } from '@/stores/admin'
  import { useAppMenu } from '@/composables/useAppMenu'

  defineOptions({ name: 'AppSidebar' })

  const route = useRoute()
  const router = useRouter()
  const { primaryMenuItems, secondaryMenuItems, tertiaryMenuItems, flowMenu } = useAppMenu()
  const { showAdministration } = storeToRefs(useAdminStore())

  // 'flow' switches the sidebar to the wizard stepper drill-down.
  const isFlowLevel = computed(() => route.meta?.menuLevel === 'flow' && !!flowMenu.value.parentItem)

  // Index of the step you're currently on — drives progressive circle fill
  // (steps up to and including the current one are filled; later ones hollow).
  const activeStepIndex = computed(() => {
    const idx = flowMenu.value.items.findIndex((i) => i.isActive)
    return idx === -1 ? 0 : idx
  })

  // The wizard route is tagged menu:'new' so it is excluded from the primary
  // group and rendered as the accent CTA button instead.
  const newItem = computed(() => {
    const r = router.getRoutes().find((r) => {
      if (r.meta?.menu !== 'new') return false
      const state = typeof r.meta?.state === 'function' ? r.meta.state(r) : 'enabled'
      return state !== 'hidden'
    })
    return r ? { name: r.name as string, title: r.meta?.title as string } : null
  })
</script>

<template>
  <aside
    class="flex h-screen w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
  >
    <!-- Brand header -->
    <div class="flex h-16 items-center border-b border-sidebar-border px-4">
      <RouterLink to="/" class="flex items-center gap-2">
        <component :is="APP_ICON" class="h-5 w-5 text-sidebar-primary" />
        <span class="text-base font-semibold text-sidebar-primary">{{ APP_NAME }}</span>
      </RouterLink>
    </div>

    <!-- App-level navigation -->
    <template v-if="!isFlowLevel">
      <nav class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-3">
        <!-- "New element" CTA -->
        <RouterLink
          v-if="newItem"
          :to="{ name: newItem.name }"
          class="mb-2 inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90"
        >
          <Plus class="h-4 w-4 shrink-0" />
          <span class="truncate">{{ newItem.title }}</span>
        </RouterLink>

        <!-- Analysis section -->
        <p class="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Analysis
        </p>
        <RouterLink
          v-for="item in primaryMenuItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="flex items-center gap-2 rounded-md border border-transparent px-3 py-2 text-sm transition-colors"
          :class="item.isActive
            ? 'border-border bg-card font-medium text-foreground'
            : 'text-sidebar-foreground hover:bg-sidebar-accent'"
        >
          <component :is="item.icon" v-if="item.icon" class="h-4 w-4 shrink-0" />
          <span class="truncate">{{ item.title }}</span>
        </RouterLink>

        <!-- Administration section (toggled in the Admin page) -->
        <template v-if="showAdministration && secondaryMenuItems.length">
          <p class="px-3 pt-4 pb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Administration
          </p>
          <RouterLink
            v-for="item in secondaryMenuItems"
            :key="item.name"
            :to="{ name: item.name }"
            class="flex items-center gap-2 rounded-md border border-transparent px-3 py-2 text-sm transition-colors"
            :class="item.isActive
              ? 'border-border bg-card font-medium text-foreground'
              : 'text-sidebar-foreground hover:bg-sidebar-accent'"
          >
            <component :is="item.icon" v-if="item.icon" class="h-4 w-4 shrink-0" />
            <span class="truncate">{{ item.title }}</span>
          </RouterLink>
        </template>
      </nav>

      <!-- Footer (tertiary: Settings, Admin) -->
      <div class="flex flex-col gap-1 border-t border-sidebar-border p-3">
        <RouterLink
          v-for="item in tertiaryMenuItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="flex items-center gap-2 rounded-md border border-transparent px-3 py-2 text-sm transition-colors"
          :class="item.isActive
            ? 'border-border bg-card font-medium text-foreground'
            : 'text-sidebar-foreground hover:bg-sidebar-accent'"
        >
          <component :is="item.icon" v-if="item.icon" class="h-4 w-4 shrink-0" />
          <span class="truncate">{{ item.title }}</span>
        </RouterLink>
      </div>
    </template>

    <!-- Flow-level navigation (wizard stepper) -->
    <nav v-else class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-3">
      <RouterLink
        :to="{ name: 'home' }"
        class="mb-3 flex items-center gap-2 rounded-md px-3 py-2 text-sm text-sidebar-foreground transition-colors hover:bg-sidebar-accent"
      >
        <MoveLeft class="h-4 w-4 shrink-0" />
        <span>Back</span>
      </RouterLink>

      <!-- Parent (non-clickable) -->
      <div class="pointer-events-none flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground">
        <component
          :is="flowMenu.parentItem.icon"
          v-if="flowMenu.parentItem?.icon"
          class="h-4 w-4 shrink-0"
        />
        <span class="truncate">{{ flowMenu.parentItem?.title }}</span>
      </div>

      <!-- Vertical stepper (ported from truenorth's AppSidebarFlowLevel).
           pl-7 reserves a left gutter; the line and every circle are centered
           at x=16px within it. Each step is a clean `relative` wrapper (the
           positioning context) holding an absolute circle gutter + the button,
           so the button's border/background never shifts the circle. -->
      <div class="relative mt-1 flex flex-col gap-1 pl-7">
        <!-- Connector line: wrapper left-0.5 (2px) + inner left-3.5 (14px) → center 16px -->
        <div class="absolute bottom-4 left-0.5 top-4 w-6">
          <div class="absolute left-3.5 h-full w-0.5 -translate-x-1/2 bg-blue-300" />
        </div>

        <div v-for="(item, index) in flowMenu.items" :key="item.name" class="relative">
          <!-- Circle gutter: -left-6 (−24px) + centered circle → center 16px, on the line -->
          <div class="absolute -left-6 top-0 bottom-0 w-6">
            <div
              class="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary transition-all"
              :class="index <= activeStepIndex ? 'h-3 w-3 bg-primary' : 'h-2 w-2 bg-background'"
            />
          </div>

          <component
            :is="item.isDisabled ? 'div' : RouterLink"
            v-bind="item.isDisabled ? {} : { to: { name: item.name } }"
            class="flex items-center gap-2 rounded-md border border-transparent px-2 py-2 text-sm transition-colors"
            :class="item.isDisabled
              ? 'cursor-default text-muted-foreground'
              : item.isActive
                ? 'border-border bg-card font-medium text-foreground'
                : 'text-sidebar-foreground hover:bg-sidebar-accent'"
          >
            <component :is="item.icon" v-if="item.icon" class="h-4 w-4 shrink-0" />
            <span class="truncate">{{ item.title }}</span>
          </component>
        </div>
      </div>
    </nav>
  </aside>
</template>

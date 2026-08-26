import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { Bot, Database, Settings, Shield } from 'lucide-vue-next'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import ExampleView from '@/views/ExampleView.vue'
import AgentsView from '@/views/AgentsView.vue'
import SettingsView from '@/views/SettingsView.vue'
import AdminView from '@/views/AdminView.vue'
import { useAdminStore } from '@/stores/admin'
import { enabledFeatureRoutes } from './features'

// ── Always-on core routes ───────────────────────────────────────────────────
// Optional blocks (wizard, charts, assistant, documents, flow) live in
// router/features.ts and are only registered when their ENABLE_* flag is on.
const coreRoutes: RouteRecordRaw[] = [
  {
    path: 'dataset',
    name: 'dataset',
    component: ExampleView,
    meta: { title: 'Datasets', icon: Database, menu: 'primary', order: 3 },
  },
]

// Administration section — visible only when the Admin toggle is on.
const adminRoutes: RouteRecordRaw[] = [
  {
    path: 'agents',
    name: 'agents',
    component: AgentsView,
    meta: { title: 'Agents', icon: Bot, menu: 'secondary', order: 1, requiresAdmin: true },
  },
]

// Footer (tertiary) routes.
const footerRoutes: RouteRecordRaw[] = [
  {
    path: 'settings',
    name: 'settings',
    component: SettingsView,
    meta: { title: 'Settings', icon: Settings, menu: 'tertiary', order: 1 },
  },
  {
    path: 'admin',
    name: 'admin',
    component: AdminView,
    meta: { title: 'Admin', icon: Shield, menu: 'tertiary', order: 2 },
  },
]

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: DefaultLayout,
    children: [
      // Root redirects to the first enabled primary route (see below).
      {
        path: '',
        name: 'home',
        redirect: () => ({ name: firstEnabledRoute() }),
        meta: { hiddenInMenu: true },
      },
      ...coreRoutes,
      ...enabledFeatureRoutes(),
      ...adminRoutes,
      ...footerRoutes,
      // Unknown / disabled-block URLs fall through to a valid page.
      {
        path: ':pathMatch(.*)*',
        name: 'notFound',
        redirect: () => ({ name: firstEnabledRoute() }),
        meta: { hiddenInMenu: true },
      },
    ],
  },
]

// When embedded in DSS, the SPA lives at a non-root path (the webapp backend
// URL). Capture the base before Vue Router takes over the pathname.
let baseUrl = '/'
if (window.self !== window.top) {
  baseUrl = window.location.pathname
}

const router = createRouter({
  history: createWebHistory(baseUrl),
  routes,
})

// First registered primary route, lowest `order` first (default: dataset).
// Used by the home redirect so it never targets a disabled block.
function firstEnabledRoute(): string {
  const primary = router
    .getRoutes()
    .filter((r) => r.meta?.menu === 'primary' && r.name)
    .sort((a, b) => ((a.meta?.order as number) ?? 0) - ((b.meta?.order as number) ?? 0))
  return (primary[0]?.name as string) ?? 'dataset'
}

// Block direct navigation to Administration pages when the toggle is off.
router.beforeEach((to) => {
  if (to.meta?.requiresAdmin && !useAdminStore().showAdministration) {
    return { name: firstEnabledRoute() }
  }
})

export default router

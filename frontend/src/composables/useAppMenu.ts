import { computed } from 'vue'
import { useRoute, useRouter, type RouteRecordNormalized } from 'vue-router'
import type { MenuItem, MenuLevel, MenuState, MenuType } from '@/types/menu'

// Build sidebar menus from the router. A page becomes a sidebar item simply by
// declaring `meta.menu` + `meta.title` + `meta.order` (see router/index.ts).
// Ported from the former truenorth `useAppMenu` — no external dependency.
export function useAppMenu() {
  const router = useRouter()
  const route = useRoute()

  const routeState = (r: RouteRecordNormalized): MenuState =>
    typeof r.meta?.state === 'function' ? r.meta.state(r) : 'enabled'

  const routeTitle = (r: RouteRecordNormalized): string =>
    typeof r.meta?.title === 'function' ? r.meta.title(r) : (r.meta?.title as string)

  const routeToMenuItem = (r: RouteRecordNormalized): MenuItem => ({
    title: routeTitle(r),
    name: r.name as string,
    icon: r.meta?.icon as MenuItem['icon'],
    isDisabled: routeState(r) === 'disabled',
    isActive:
      r.name === route.name ||
      !!(route.matched.length > 2 && route.matched.slice(1).some((m) => m.name === r.name)),
    menuLevel: r.meta?.menuLevel as MenuLevel | undefined,
  })

  const validRoutes = (routes: RouteRecordNormalized[]) =>
    routes
      .filter((r) => r.name && r.meta?.title && !r.meta?.hiddenInMenu)
      .filter((r) => routeState(r) !== 'hidden')
      .sort((a, b) => ((a.meta?.order as number) ?? 0) - ((b.meta?.order as number) ?? 0))

  const itemsByMenu = (menu: MenuType) =>
    validRoutes(router.getRoutes())
      .filter((r) => r.meta?.menu === menu)
      .map(routeToMenuItem)

  const primaryMenuItems = computed(() => itemsByMenu('primary'))
  const secondaryMenuItems = computed(() => itemsByMenu('secondary'))
  const tertiaryMenuItems = computed(() => itemsByMenu('tertiary'))

  // Wizard drill-down: the matched parent (menuLevel:'flow') and its child steps.
  // Children are derived from the flattened route table by path prefix, so we
  // don't depend on RouteRecordNormalized exposing `.children`.
  const flowMenu = computed<{ parentItem: MenuItem | null; items: MenuItem[] }>(() => {
    const parent =
      route.meta?.menuLevel === 'flow'
        ? (route.matched.find((m) => m.meta?.menuLevel === 'flow') ?? null)
        : null
    if (!parent) return { parentItem: null, items: [] }
    const children = router
      .getRoutes()
      .filter((r) => r.name !== parent.name && r.path.startsWith(`${parent.path}/`))
    return {
      parentItem: routeToMenuItem(parent as RouteRecordNormalized),
      items: validRoutes(children).map(routeToMenuItem),
    }
  })

  return { primaryMenuItems, secondaryMenuItems, tertiaryMenuItems, flowMenu }
}

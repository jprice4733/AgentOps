import type { Component } from 'vue'
import type { RouteRecordNormalized } from 'vue-router'

// Sidebar section a route belongs to (drives which group it renders under).
export type MenuType = 'primary' | 'secondary' | 'tertiary'

// Navigation mode: 'app' = normal sidebar; 'flow' = wizard stepper drill-down.
export type MenuLevel = 'app' | 'flow'

// A route's runtime state, returned by `meta.state(route)`:
//  - 'enabled'  → visible & clickable
//  - 'disabled' → visible but greyed/non-clickable (wizard stepper steps)
//  - 'hidden'   → removed from the menu entirely
export type MenuState = 'enabled' | 'disabled' | 'hidden'

// Route `meta` shape the sidebar understands. Extend as needed.
export interface AppRouteMeta {
  title?: string | ((route: RouteRecordNormalized) => string)
  icon?: Component
  menu?: MenuType | 'new'
  menuLevel?: MenuLevel
  order?: number
  hiddenInMenu?: boolean
  requiresAdmin?: boolean
  state?: (route: RouteRecordNormalized) => MenuState
}

// A renderable sidebar item derived from a route.
export interface MenuItem {
  title: string
  name: string
  icon?: Component
  isActive: boolean
  isDisabled?: boolean
  menuLevel?: MenuLevel
}

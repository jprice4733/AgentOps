// App identity — the display name comes from `VITE_APP_NAME` in app.env;
// the icon is a fixed brand mark. No per-app code edits needed for setup.

import { Blocks } from 'lucide-vue-next'
import type { Component } from 'vue'

/** Human-readable name shown in the sidebar header (set VITE_APP_NAME in app.env). */
export const APP_NAME: string = import.meta.env.VITE_APP_NAME ?? ''

/** Icon component shown next to the app name in the sidebar.
 *  Swap `Blocks` for any other lucide-vue-next icon if you want a different mark. */
export const APP_ICON: Component = Blocks

// ── Optional building block flags ─────────────────────────────────────────────
// Set ENABLE_* in app.env — one line per flag controls both backend and frontend.
// Vite bakes them into the bundle at build time; they cannot change at runtime.
export const ENABLE_DOCUMENTS: boolean = import.meta.env.ENABLE_DOCUMENTS === '1'
export const ENABLE_CHATBOT: boolean   = import.meta.env.ENABLE_CHATBOT === '1'
export const ENABLE_WIZARD: boolean    = import.meta.env.ENABLE_WIZARD === '1'
export const ENABLE_CHARTS: boolean    = import.meta.env.ENABLE_CHARTS === '1'
export const ENABLE_FLOW: boolean      = import.meta.env.ENABLE_FLOW === '1'

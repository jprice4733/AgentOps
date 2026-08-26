/**
 * Settings store — app settings persisted to DSS project variables via the API.
 *
 * Loaded lazily on the Settings view (ensureLoaded). Includes the list of
 * available LLMs fetched from /api/system/llms.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiUrl } from '@/utils/api'

export interface LlmOption {
  id: string
  label: string
  type: string
  provider: string
}

export interface AppSettings {
  llm_id: string | null
  // ── Documents block ────────────────────────────────────────────────────────
  /** Cached DSS managed-folder id (set by the backend on first upload). */
  documents_folder_id?: string | null
  // ── Chatbot block ──────────────────────────────────────────────────────────
  /** Per-tool policy: "allow" runs immediately, "prompt" asks for approval. */
  tool_permissions?: Record<string, string>
  /** Skip all approval prompts (master override). */
  accept_all_mode?: boolean
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<AppSettings>({ llm_id: null })
  const llms = ref<LlmOption[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  let fetchStarted = false

  async function ensureLoaded() {
    if (fetchStarted) return
    fetchStarted = true
    isLoading.value = true
    try {
      const [sRes, lRes] = await Promise.all([
        fetch(apiUrl('/api/system/settings')),
        fetch(apiUrl('/api/system/llms')),
      ])
      if (!sRes.ok) throw new Error(`settings: HTTP ${sRes.status}`)
      if (!lRes.ok) throw new Error(`llms: HTTP ${lRes.status}`)
      settings.value = (await sRes.json()) as AppSettings
      llms.value = (await lRes.json()) as LlmOption[]
      error.value = null
    } catch (e) {
      fetchStarted = false // allow retry on next visit
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      isLoading.value = false
    }
  }

  async function updateSettings(patch: Partial<AppSettings>) {
    const res = await fetch(apiUrl('/api/system/settings'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (!res.ok) throw new Error(`PUT /api/system/settings: HTTP ${res.status}`)
    settings.value = (await res.json()) as AppSettings
  }

  return { settings, llms, isLoading, error, ensureLoaded, updateSettings }
})

// Sidebar section visibility — persisted per-browser in localStorage.
// Toggled from the Admin page (views/AdminView.vue); the sidebar and a
// router guard both react to it.

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'blueprint.admin'

function loadFromStorage(): boolean | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return Boolean((JSON.parse(raw) as { showAdministration?: boolean }).showAdministration)
  } catch {
    return null
  }
}

export const useAdminStore = defineStore('admin', () => {
  // Default ON: the blueprint showcases all blocks. Flip to false for real apps.
  const showAdministration = ref<boolean>(loadFromStorage() ?? true)

  watch(showAdministration, (v) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ showAdministration: v }))
    } catch {
      /* localStorage unavailable (e.g. blocked third-party storage) */
    }
  })

  return { showAdministration }
})

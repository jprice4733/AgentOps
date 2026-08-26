import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiUrl } from '@/utils/api'
import type { Agent } from '@/types/agents'

export const useAgentsStore = defineStore('agents', () => {
  const agents = ref<Agent[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadAgents(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(apiUrl('/api/agents/sample'))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      agents.value = (await res.json()) as Agent[]
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  return { agents, loading, error, loadAgents }
})

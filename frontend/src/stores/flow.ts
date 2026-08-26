import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiUrl } from '@/utils/api'
import type { FlowSample } from '@/types/flow'

export const useFlowStore = defineStore('flow', () => {
  const sample = ref<FlowSample | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadSample(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(apiUrl('/api/flow/sample'))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      sample.value = (await res.json()) as FlowSample
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  return { sample, loading, error, loadSample }
})

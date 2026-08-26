import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiUrl } from '@/utils/api'
import type { Document } from '@/types/documents'

export const useDocumentsStore = defineStore('documents', () => {
  const documents = ref<Document[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadAll(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(apiUrl('/api/documents'))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      documents.value = (await res.json()) as Document[]
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function upload(files: File[]): Promise<void> {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const res = await fetch(apiUrl('/api/documents'), { method: 'POST', body: form })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    const created = (await res.json()) as Document[]
    documents.value = [...created, ...documents.value]
  }

  async function rename(id: string, filename: string): Promise<void> {
    const res = await fetch(apiUrl(`/api/documents/${id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    const updated = (await res.json()) as Document
    documents.value = documents.value.map((d) => (d.id === id ? updated : d))
  }

  async function remove(id: string): Promise<void> {
    const res = await fetch(apiUrl(`/api/documents/${id}`), { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    documents.value = documents.value.filter((d) => d.id !== id)
  }

  async function redescribe(id: string): Promise<void> {
    const res = await fetch(apiUrl(`/api/documents/${id}/redescribe`), { method: 'POST' })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    documents.value = documents.value.map((d) =>
      d.id === id ? { ...d, status: 'describing', error: null } : d,
    )
  }

  /** Refresh a single document's metadata (used during polling). */
  async function refreshOne(_id: string): Promise<void> {
    try {
      await loadAll()
    } catch {
      // Polling — swallow errors silently
    }
  }

  return { documents, loading, error, loadAll, upload, rename, remove, redescribe, refreshOne }
})

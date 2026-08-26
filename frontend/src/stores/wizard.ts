import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiUrl } from '@/utils/api'
import type { WizardSubmission, WizardResult } from '@/types/wizard'

export const useWizardStore = defineStore('wizard', () => {
  // Form fields — kept in the store so they survive step navigation.
  const name = ref('')
  const category = ref('')
  const notes = ref('')

  // Submission lifecycle.
  const progress = ref<'idle' | 'saving' | 'done' | 'error'>('idle')
  const result = ref<WizardResult | null>(null)
  const errorMessage = ref<string | null>(null)

  /** True when all required fields for the given step are filled. */
  function isStepComplete(step: number): boolean {
    if (step === 0) return name.value.trim().length > 0 && category.value.length > 0
    // Step 1 (notes) is optional — always allow proceeding.
    return true
  }

  /** POST the collected payload to /api/wizard/submit. */
  async function submit(): Promise<void> {
    progress.value = 'saving'
    errorMessage.value = null
    const payload: WizardSubmission = {
      name: name.value.trim(),
      category: category.value,
      notes: notes.value.trim(),
    }
    try {
      const res = await fetch(apiUrl('/api/wizard/submit'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
      }
      result.value = (await res.json()) as WizardResult
      progress.value = 'done'
    } catch (e) {
      errorMessage.value = e instanceof Error ? e.message : String(e)
      progress.value = 'error'
    }
  }

  /** Reset all fields and progress so the wizard can be used again. */
  function reset(): void {
    name.value = ''
    category.value = ''
    notes.value = ''
    progress.value = 'idle'
    result.value = null
    errorMessage.value = null
  }

  return { name, category, notes, progress, result, errorMessage, isStepComplete, submit, reset }
})

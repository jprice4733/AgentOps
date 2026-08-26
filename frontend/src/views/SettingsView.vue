<script setup lang="ts">
  /**
   * SettingsView — app settings persisted to DSS project variables.
   *
   * Currently: LLM picker (which model the app uses for AI-assisted features).
   * Add more settings sections below as your app grows.
   *
   * Settings are stored under the key `<prefix>_app_settings` in the project's
   * "standard" variables, so they survive webapp restarts.
   */
  import { onMounted, computed, ref } from 'vue'
  import { Loader2 } from 'lucide-vue-next'
  import { EaSelect } from '@/components/ui'
  import { useSettingsStore } from '@/stores/settings'
  import { ENABLE_CHATBOT } from '@/config'
  import { apiUrl } from '@/utils/api'

  defineOptions({ name: 'SettingsView' })

  const store = useSettingsStore()
  const savingLlm = ref(false)
  const llmError = ref<string | null>(null)

  // ── Tool permissions (CHATBOT block) ──────────────────────────────────────
  interface ToolInfo { name: string; description: string; policy: string }
  const toolList = ref<ToolInfo[]>([])
  const acceptAll = computed(() => store.settings.accept_all_mode ?? false)

  async function loadTools() {
    if (!ENABLE_CHATBOT) return
    try {
      const res = await fetch(apiUrl('/api/chat/tools'))
      if (res.ok) toolList.value = (await res.json()) as ToolInfo[]
    } catch { /* non-fatal */ }
  }

  async function setToolPolicy(toolName: string, policy: string) {
    const current: Record<string, string> = { ...(store.settings.tool_permissions ?? {}) }
    current[toolName] = policy
    await store.updateSettings({ tool_permissions: current })
  }

  async function toggleAcceptAll() {
    await store.updateSettings({ accept_all_mode: !acceptAll.value })
  }

  onMounted(async () => {
    await store.ensureLoaded()
    await loadTools()
  })

  const llmOptions = computed(() =>
    store.llms.map((l) => ({ value: l.id, label: l.label }))
  )

  async function onLlmChange(value: string | undefined) {
    savingLlm.value = true
    llmError.value = null
    try {
      await store.updateSettings({ llm_id: value ?? null })
    } catch (e) {
      llmError.value = e instanceof Error ? e.message : String(e)
    } finally {
      savingLlm.value = false
    }
  }
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="shrink-0 h-16 border-b px-8 flex flex-col justify-center">
      <h1 class="text-xl font-semibold tracking-tight">Settings</h1>
      <p class="text-sm text-muted-foreground mt-0.5">Application configuration — persisted to DSS project variables.</p>
    </header>
    <div class="flex-1 overflow-auto">
    <div class="max-w-3xl mx-auto p-8 space-y-8">

      <!-- LLM selection -->
      <section class="border rounded-lg bg-white">
        <div class="px-5 py-4 border-b">
          <h2 class="text-base font-semibold">Language model</h2>
          <p class="text-xs text-muted-foreground mt-1">
            The LLM used for AI-assisted features across the app.
            Populated from LLMs configured in your DSS project.
          </p>
        </div>
        <div class="px-5 py-4 space-y-2">
          <label class="text-xs font-medium text-muted-foreground">LLM</label>
          <div class="flex items-center gap-2">
            <EaSelect
              class="flex-1 min-w-0"
              placeholder="— Select an LLM —"
              :model-value="store.settings.llm_id ?? undefined"
              :options="llmOptions"
              :disabled="store.isLoading || savingLlm"
              @update:model-value="onLlmChange"
            />
            <Loader2
              v-if="store.isLoading || savingLlm"
              class="w-4 h-4 animate-spin text-muted-foreground shrink-0"
            />
          </div>
          <p v-if="store.error" class="text-xs text-destructive">
            Could not load LLMs: {{ store.error }}
          </p>
          <p v-if="llmError" class="text-xs text-destructive">
            Save failed: {{ llmError }}
          </p>
          <p v-if="!store.isLoading && llmOptions.length === 0 && !store.error"
             class="text-xs text-muted-foreground">
            No LLMs found. Add a model in your DSS project's LLM settings.
          </p>
        </div>
      </section>

      <!-- ── Chatbot: tool permissions ──────────────────────────────────── -->
      <section v-if="ENABLE_CHATBOT" class="border rounded-lg bg-white">
        <div class="px-5 py-4 border-b">
          <h2 class="text-base font-semibold">Tool permissions</h2>
          <p class="text-xs text-muted-foreground mt-1">
            Control which agent tools require your approval before running.
            <strong>Allow</strong>: run automatically. <strong>Prompt</strong>: ask you first.
          </p>
        </div>
        <div class="px-5 py-4 space-y-3">
          <!-- Accept-all master switch -->
          <div class="flex items-center justify-between py-1">
            <div>
              <p class="text-sm font-medium">Accept all (no prompts)</p>
              <p class="text-xs text-muted-foreground">Skip approval for every tool. Use with care.</p>
            </div>
            <button
              class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none"
              :class="acceptAll ? 'bg-primary' : 'bg-muted'"
              @click="toggleAcceptAll"
            >
              <span
                class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform"
                :class="acceptAll ? 'translate-x-4' : 'translate-x-0.5'"
              />
            </button>
          </div>
          <hr class="border-border" />
          <!-- Per-tool policy -->
          <div
            v-for="tool in toolList"
            :key="tool.name"
            class="flex items-center justify-between py-1"
          >
            <div>
              <p class="text-sm font-mono font-medium">{{ tool.name }}</p>
              <p class="text-xs text-muted-foreground">{{ tool.description }}</p>
            </div>
            <select
              :value="(store.settings.tool_permissions ?? {})[tool.name] ?? tool.policy"
              class="text-xs border rounded px-2 py-1 bg-background"
              :disabled="acceptAll"
              @change="setToolPolicy(tool.name, ($event.target as HTMLSelectElement).value)"
            >
              <option value="allow">Allow</option>
              <option value="prompt">Prompt</option>
            </select>
          </div>
        </div>
      </section>

      <!-- ── Add more settings sections here ─────────────────────────────── -->
      <!-- Pattern:
           1. Add a key to ALLOWED_KEYS in backend/services/settings.py
           2. Add it to AppSettings interface in frontend/src/stores/settings.ts
           3. Add a section below similar to the LLM section above
      -->

    </div>
    </div>
  </div>
</template>

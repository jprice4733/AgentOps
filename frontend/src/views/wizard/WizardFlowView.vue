<script setup lang="ts">
/**
 * WizardFlowView — multi-step guided creation flow.
 *
 * A hello-world example of the routed "wizard" pattern: each step is a child
 * route (its own URL), and the app sidebar switches to a flow-level vertical
 * stepper automatically — AppSidebar renders any route tree tagged
 * `meta.menuLevel: 'flow'` as connected step circles. Steps whose
 * `meta.state()` returns 'disabled' show as hollow, non-clickable circles.
 *
 * This shell owns the header (step title + description), the footer
 * navigation (Back / Next / Create), and the success panel. The step content
 * itself lives in the child views (WizardStepBasics / Details / Review).
 *
 * The backend validates the final payload (Pydantic) and returns a result.
 * No DSS dependency — replace the static result logic in backend/routes/wizard.py
 * with a real persist call when you're ready.
 *
 * Enabled when ENABLE_WIZARD=1 in app.env.
 */
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { WandSparkles } from 'lucide-vue-next'
import { EaButton, EaEmpty } from '@/components/ui'
import { useWizardStore } from '@/stores/wizard'

defineOptions({ name: 'WizardFlowView' })

const route = useRoute()
const router = useRouter()
const store = useWizardStore()

const STEP_ROUTE_NAMES = ['wizardBasics', 'wizardDetails', 'wizardReview'] as const

const STEP_DESCRIPTIONS: Record<string, string> = {
  wizardBasics: 'Name your element and pick a category.',
  wizardDetails: 'Add optional notes or context.',
  wizardReview: 'Review your entries before creating.',
}

const currentStepIndex = computed(() =>
  STEP_ROUTE_NAMES.indexOf(route.name as (typeof STEP_ROUTE_NAMES)[number]),
)
const isLast = computed(() => currentStepIndex.value === STEP_ROUTE_NAMES.length - 1)

const stepTitle = computed(() => (route.meta.title as string) ?? '')
const stepDescription = computed(() => STEP_DESCRIPTIONS[route.name as string] ?? '')

function next() {
  if (!store.isStepComplete(currentStepIndex.value)) return
  const target = STEP_ROUTE_NAMES[currentStepIndex.value + 1]
  if (target) router.push({ name: target })
}

function back() {
  const target = STEP_ROUTE_NAMES[currentStepIndex.value - 1]
  if (target) router.push({ name: target })
}

async function create() {
  await store.submit()
}

function restart() {
  store.reset()
  router.push({ name: STEP_ROUTE_NAMES[0] })
}

// Deep-link guard: landing mid-flow with incomplete earlier steps jumps back
// to the first incomplete one.
onMounted(() => {
  for (let i = 0; i < currentStepIndex.value; i++) {
    if (!store.isStepComplete(i)) {
      router.replace({ name: STEP_ROUTE_NAMES[i] })
      return
    }
  }
})
</script>

<template>
  <div class="h-full flex flex-col">

    <!-- ── Success ─────────────────────────────────────────────────────── -->
    <template v-if="store.progress === 'done' && store.result">
      <div class="flex-1 overflow-auto">
        <div class="max-w-2xl mx-auto p-8">
          <div class="border rounded-lg p-6 space-y-4 bg-muted/30">
            <EaEmpty
              :icon="WandSparkles"
              title="Created successfully"
              :description="store.result.summary"
            />
            <p class="text-xs text-center text-muted-foreground font-mono">
              id: {{ store.result.id }}
            </p>
            <div class="flex justify-center">
              <EaButton variant="outline" @click="restart">Start over</EaButton>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ── Wizard ──────────────────────────────────────────────────────── -->
    <template v-else>

      <!-- h-16 matches the sidebar header so this divider lines up with the
           horizontal rule under the app name (same fix as the Assistant view). -->
      <header class="shrink-0 h-16 border-b px-8 flex flex-col justify-center">
        <h1 class="text-xl font-semibold tracking-tight">{{ stepTitle }}</h1>
        <p class="text-sm text-muted-foreground mt-0.5">{{ stepDescription }}</p>
      </header>

      <div class="flex-1 overflow-auto px-8 py-6">
        <div class="max-w-2xl mx-auto">
          <router-view />
        </div>
      </div>

      <footer class="shrink-0 border-t px-8 py-4 flex items-center justify-between gap-3">
        <EaButton
          variant="outline"
          :disabled="currentStepIndex === 0"
          @click="back"
        >
          Back
        </EaButton>

        <div class="flex items-center gap-3">
          <span v-if="store.progress === 'error'" class="text-sm text-destructive">
            {{ store.errorMessage }}
          </span>

          <EaButton
            v-if="!isLast"
            variant="primary"
            :disabled="!store.isStepComplete(currentStepIndex)"
            @click="next"
          >
            Next
          </EaButton>
          <EaButton
            v-else
            variant="primary"
            :disabled="store.progress === 'saving'"
            @click="create"
          >
            {{ store.progress === 'saving' ? 'Creating…' : 'Create' }}
          </EaButton>
        </div>
      </footer>

    </template>

  </div>
</template>

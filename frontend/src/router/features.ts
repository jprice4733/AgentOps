import {
  AlignLeft,
  BarChart2,
  CheckCircle2,
  FileText,
  MessageSquare,
  PencilLine,
  Wand2,
  Workflow,
} from 'lucide-vue-next'
import type { RouteRecordRaw } from 'vue-router'
import WizardFlowView from '@/views/wizard/WizardFlowView.vue'
import WizardStepBasics from '@/views/wizard/WizardStepBasics.vue'
import WizardStepDetails from '@/views/wizard/WizardStepDetails.vue'
import WizardStepReview from '@/views/wizard/WizardStepReview.vue'
import ChartsView from '@/views/ChartsView.vue'
import FlowView from '@/views/FlowView.vue'
import DocumentsView from '@/views/DocumentsView.vue'
import AssistantView from '@/views/AssistantView.vue'
import { useWizardStore } from '@/stores/wizard'
import {
  ENABLE_CHATBOT,
  ENABLE_CHARTS,
  ENABLE_DOCUMENTS,
  ENABLE_FLOW,
  ENABLE_WIZARD,
} from '@/config'

// ── Optional building-block registry ────────────────────────────────────────
// Each block contributes its route(s), gated by its ENABLE_* flag. A disabled
// block is simply NOT registered: the sidebar omits it, and its URL falls
// through to the catch-all redirect — no per-feature guard needed.
//
// View components are still statically imported (the single-bundle constraint
// rules out runtime `import()`), but only the routes of enabled blocks are
// added to the router.
interface FeatureBlock {
  enabled: boolean
  routes: RouteRecordRaw[]
}

const blocks: FeatureBlock[] = [
  {
    enabled: ENABLE_WIZARD,
    routes: [
      {
        path: 'wizard',
        name: 'wizard',
        component: WizardFlowView,
        redirect: { name: 'wizardBasics' },
        meta: {
          title: 'New element',
          icon: Wand2,
          // menu:'new' renders this as the accent CTA (not in the primary list).
          menu: 'new',
          // menuLevel:'flow' switches the sidebar to the vertical stepper.
          menuLevel: 'flow',
          order: 0,
        },
        children: [
          {
            path: 'basics',
            name: 'wizardBasics',
            component: WizardStepBasics,
            meta: { menuLevel: 'flow', title: 'Basics', icon: PencilLine, order: 0 },
          },
          {
            path: 'details',
            name: 'wizardDetails',
            component: WizardStepDetails,
            meta: {
              menuLevel: 'flow',
              title: 'Details',
              icon: AlignLeft,
              order: 1,
              // 'disabled' renders a hollow, non-clickable stepper circle until
              // the Basics step is complete.
              state: () => (useWizardStore().isStepComplete(0) ? 'enabled' : 'disabled'),
            },
          },
          {
            path: 'review',
            name: 'wizardReview',
            component: WizardStepReview,
            meta: {
              menuLevel: 'flow',
              title: 'Review',
              icon: CheckCircle2,
              order: 2,
              state: () => (useWizardStore().isStepComplete(0) ? 'enabled' : 'disabled'),
            },
          },
        ],
      },
    ],
  },
  {
    enabled: ENABLE_CHARTS,
    routes: [
      {
        path: 'charts',
        name: 'charts',
        component: ChartsView,
        meta: { title: 'Charts', icon: BarChart2, menu: 'primary', order: 1 },
      },
    ],
  },
  {
    enabled: ENABLE_CHATBOT,
    routes: [
      {
        path: 'assistant',
        name: 'assistant',
        component: AssistantView,
        meta: { title: 'Assistant', icon: MessageSquare, menu: 'primary', order: 2 },
      },
    ],
  },
  {
    enabled: ENABLE_DOCUMENTS,
    routes: [
      {
        path: 'documents',
        name: 'documents',
        component: DocumentsView,
        meta: { title: 'Documents', icon: FileText, menu: 'primary', order: 4 },
      },
    ],
  },
  {
    enabled: ENABLE_FLOW,
    routes: [
      {
        path: 'flow',
        name: 'flow',
        component: FlowView,
        meta: { title: 'Flow', icon: Workflow, menu: 'primary', order: 5 },
      },
    ],
  },
]

// Routes for all currently-enabled blocks, flattened.
export function enabledFeatureRoutes(): RouteRecordRaw[] {
  return blocks.filter((b) => b.enabled).flatMap((b) => b.routes)
}

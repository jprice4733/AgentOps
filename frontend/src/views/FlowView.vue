<script setup lang="ts">
/**
 * FlowView — Vue Flow node/edge graph demo.
 *
 * Renders a small directed graph (4 nodes, 3 edges) fetched from the backend.
 * Each node uses a custom card component (FlowNode.vue) with an icon and
 * palette that reflects the node's pipeline stage (source / transform /
 * enrich / output).
 *
 * To make it real, replace GET /api/flow/sample with a DSS project-flow query
 * or any domain graph. For automatic layout of large graphs, add
 * @dagrejs/dagre and compute positions on the frontend.
 *
 * Requires @vue-flow/core/dist/style.css (imported in frontend/src/style.css).
 *
 * Enabled when ENABLE_FLOW=1 in app.env.
 */
import { computed, markRaw, onMounted } from 'vue'
import { Workflow } from 'lucide-vue-next'
import { EaEmpty } from '@/components/ui'
import { VueFlow, MarkerType } from '@vue-flow/core'
import type { Edge, Node, NodeTypesObject } from '@vue-flow/core'
import { useFlowStore } from '@/stores/flow'
import FlowNodeComponent from '@/components/flow/FlowNode.vue'

defineOptions({ name: 'FlowView' })

const store = useFlowStore()
onMounted(() => store.loadSample())

// Register the custom node type — markRaw prevents Vue from making the
// component reactive, which would break vue-flow's internal rendering.
const nodeTypes = { 'flow-node': markRaw(FlowNodeComponent) } as NodeTypesObject

const defaultEdgeOptions = {
  style: { stroke: 'hsl(233.92, 50%, 35%)', strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: 'hsl(233.92, 50%, 35%)' },
}

const nodes = computed<Node[]>(() =>
  (store.sample?.nodes ?? []).map((n) => ({
    id: n.id,
    type: 'flow-node',
    position: { x: n.x, y: n.y },
    data: { label: n.label, nodeType: n.node_type },
  })),
)

const edges = computed<Edge[]>(() =>
  (store.sample?.edges ?? []).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
  })),
)
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">

    <!-- Header -->
    <header class="shrink-0 h-16 border-b px-8 flex flex-col justify-center">
      <h1 class="text-xl font-semibold tracking-tight">Flow</h1>
      <p class="text-sm text-muted-foreground mt-0.5">A node/edge graph rendered from a backend endpoint.</p>
    </header>

    <!-- Loading -->
    <div v-if="store.loading" class="flex-1 flex items-center justify-center">
      <div class="w-8 h-8 rounded-full bg-muted animate-pulse" />
    </div>

    <!-- Error -->
    <div v-else-if="store.error" class="flex-1 flex items-center justify-center p-8">
      <EaEmpty
        :icon="Workflow"
        title="Could not load graph data"
        :description="store.error"
      />
    </div>

    <!-- Flow canvas -->
    <div
      v-else
      class="flex-1 min-h-96 m-8 border rounded-lg overflow-hidden flow-container"
    >
      <VueFlow
        :nodes="nodes"
        :edges="edges"
        :node-types="nodeTypes"
        :default-edge-options="defaultEdgeOptions"
        :fit-view-on-init="true"
      />
    </div>

  </div>
</template>

<style scoped>
/* Dot-grid canvas background matching the mockup_reasoning architecture view. */
.flow-container :deep(.vue-flow) {
  background-color: hsl(0 0% 100%);
  background-image: radial-gradient(hsl(240 5.9% 90%) 1px, transparent 1px);
  background-size: 18px 18px;
}

.flow-container :deep(.vue-flow__attribution) {
  display: none;
}
</style>

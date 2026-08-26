<script setup lang="ts">
  /**
   * ExampleView — demonstrates the full FE ↔ BE ↔ DSS path.
   *
   * 1. On mount, fetches /api/example/datasets to populate the selector.
   * 2. On dataset selection, fetches /api/example/preview?name=X&limit=20.
   * 3. Renders the rows in a polished table with column types and sorting.
   *
   * Replace with your own domain view. The apiUrl() helper and the fetch
   * pattern here are the idioms to carry over.
   */
  import { computed, onMounted, ref } from 'vue'
  import { Database } from 'lucide-vue-next'
  import { EaSelect, EaEmpty } from '@/components/ui'
  import { apiUrl } from '@/utils/api'
  import { getNextSortState, sortRows, type SortState } from '@/utils/sorting'
  import DataPreview from '@/components/data/DataPreview.vue'

  defineOptions({ name: 'ExampleView' })

  interface DatasetInfo {
    name: string
    type: string
  }

  interface PreviewData {
    columns: string[]
    rows: (string | number | boolean | null)[][]
    row_count: number
    schema: Record<string, string>
    _note?: string
  }

  // ── State ──────────────────────────────────────────────────────────────────
  const datasets = ref<DatasetInfo[]>([])
  const selectedName = ref<string | undefined>()
  const preview = ref<PreviewData | null>(null)
  const sortState = ref<SortState | null>(null)

  const loadingDatasets = ref(false)
  const loadingPreview = ref(false)
  const datasetsError = ref<string | null>(null)
  const previewError = ref<string | null>(null)

  // ── Dataset list ───────────────────────────────────────────────────────────
  onMounted(async () => {
    loadingDatasets.value = true
    datasetsError.value = null
    try {
      const res = await fetch(apiUrl('/api/example/datasets'))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      datasets.value = (await res.json()) as DatasetInfo[]
    } catch (e) {
      datasetsError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingDatasets.value = false
    }
  })

  const datasetOptions = computed(() =>
    datasets.value.map((d) => ({ value: d.name, label: d.name })),
  )

  // ── Dataset preview ────────────────────────────────────────────────────────
  async function onDatasetSelect(name: string | undefined) {
    selectedName.value = name
    preview.value = null
    previewError.value = null
    sortState.value = null
    if (!name) return

    loadingPreview.value = true
    try {
      const res = await fetch(apiUrl(`/api/example/preview?name=${encodeURIComponent(name)}`))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      preview.value = (await res.json()) as PreviewData
    } catch (e) {
      previewError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingPreview.value = false
    }
  }

  // ── Row transformation: cell arrays → keyed objects (for DataPreview) ──────
  const rowObjects = computed<Record<string, unknown>[]>(() => {
    if (!preview.value) return []
    const { columns, rows } = preview.value
    return rows.map((row) => Object.fromEntries(columns.map((col, i) => [col, row[i]])))
  })

  // ── Sorted rows (client-side, over the loaded page) ───────────────────────
  const sortedRows = computed(() => sortRows(rowObjects.value, sortState.value))

  function handleSort(column: string) {
    sortState.value = getNextSortState(sortState.value, column)
  }
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="shrink-0 h-16 border-b px-8 flex flex-col justify-center">
      <h1 class="text-xl font-semibold tracking-tight">Datasets</h1>
      <p class="text-sm text-muted-foreground mt-0.5">Select a dataset to preview its rows.</p>
    </header>
    <div class="flex-1 overflow-auto">
    <div class="max-w-5xl mx-auto p-8 space-y-6">

      <!-- Dataset selector -->
      <div class="flex items-center gap-3">
        <EaSelect
          class="w-72"
          placeholder="— Select a dataset —"
          :options="datasetOptions"
          :disabled="loadingDatasets"
          :model-value="selectedName"
          @update:model-value="onDatasetSelect"
        />
        <span
          v-if="datasets.length"
          class="text-xs text-muted-foreground"
        >
          {{ datasets.length }} dataset{{ datasets.length !== 1 ? 's' : '' }}
        </span>
      </div>

      <!-- Errors -->
      <p v-if="datasetsError" class="text-sm text-destructive">
        Could not load datasets: {{ datasetsError }}
      </p>

      <!-- Empty state (no selection yet) -->
      <EaEmpty
        v-if="!selectedName && !loadingDatasets && !datasetsError"
        :icon="Database"
        title="No dataset selected"
        description="Pick a dataset above to preview its rows."
      />

      <!-- Preview area -->
      <template v-if="selectedName">
        <div
          v-if="preview && !loadingPreview"
          class="border rounded-lg overflow-hidden"
        >
          <!-- Header bar: name + row count -->
          <div class="px-4 py-2.5 border-b bg-muted/30 flex items-center justify-between">
            <span class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {{ selectedName }}
            </span>
            <span class="text-xs text-muted-foreground">
              {{ preview.row_count }} row{{ preview.row_count !== 1 ? 's' : '' }} shown
            </span>
          </div>

          <!-- Backend note (e.g. iter_rows unavailable) -->
          <p v-if="preview._note" class="px-4 py-1.5 text-xs text-muted-foreground italic border-b">
            {{ preview._note }}
          </p>

          <div class="p-2">
            <DataPreview
              :rows="sortedRows"
              :columns="preview.columns"
              :schema="preview.schema"
              :error="previewError"
              @sort="handleSort"
            />
          </div>
        </div>

        <!-- Loading skeleton -->
        <div v-else-if="loadingPreview" class="border rounded-lg overflow-hidden">
          <div class="px-4 py-2.5 border-b bg-muted/30">
            <div class="h-3 w-32 bg-muted animate-pulse rounded" />
          </div>
          <div class="p-4 space-y-2">
            <div v-for="i in 5" :key="i" class="h-3 bg-muted animate-pulse rounded" />
          </div>
        </div>

        <!-- Preview error -->
        <p v-else-if="previewError" class="text-sm text-destructive">
          Preview failed: {{ previewError }}
        </p>
      </template>

    </div>
    </div>
  </div>
</template>

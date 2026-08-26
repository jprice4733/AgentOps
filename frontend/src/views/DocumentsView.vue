<script setup lang="ts">
/**
 * DocumentsView — file upload/management UI for the Documents building block.
 *
 * Enabled when ENABLE_DOCUMENTS=1 in app.env.
 * Files are stored in a DSS Managed Folder; metadata in SQLite.
 *
 * Key patterns:
 *  - apiUrl() for every fetch (iframe path fix — see README "non-obvious bits")
 *  - local Ea* components only (EaSelect, EaEmpty) — no @tanstack/vue-table
 *  - design tokens only (text-muted-foreground, bg-muted/30, etc.) — no raw hex
 *  - polling while any doc is status "describing" (ENABLE_DESCRIBE=1 case)
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  CheckCircle2,
  AlertTriangle,
  Download,
  FileText,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  Upload,
} from 'lucide-vue-next'
import { EaEmpty } from '@/components/ui'
import { useDocumentsStore } from '@/stores/documents'
import { apiUrl } from '@/utils/api'
import type { Document } from '@/types/documents'

defineOptions({ name: 'DocumentsView' })

const store = useDocumentsStore()

// ── Upload ─────────────────────────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadError = ref<string | null>(null)
const isDragging = ref(false)

async function handleFiles(files: FileList | File[]) {
  const list = Array.from(files)
  if (!list.length) return
  uploading.value = true
  uploadError.value = null
  try {
    await store.upload(list)
    startPollingIfNeeded()
  } catch (e) {
    uploadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    uploading.value = false
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

function onFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) handleFiles(input.files)
}
function onDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files) handleFiles(e.dataTransfer.files)
}

// ── Inline rename ─────────────────────────────────────────────────────────────
const renamingId = ref<string | null>(null)
const renameValue = ref('')
const renameError = ref<string | null>(null)

function startRename(doc: Document) {
  renamingId.value = doc.id
  renameValue.value = doc.filename
  renameError.value = null
}

async function commitRename(id: string) {
  try {
    await store.rename(id, renameValue.value)
    renamingId.value = null
  } catch (e) {
    renameError.value = e instanceof Error ? e.message : String(e)
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────
const deletingId = ref<string | null>(null)

async function confirmDelete(id: string) {
  deletingId.value = id
  try {
    await store.remove(id)
  } finally {
    deletingId.value = null
  }
}

// ── Redescribe ────────────────────────────────────────────────────────────────
async function redescribe(id: string) {
  await store.redescribe(id)
  startPollingIfNeeded()
}

// ── Status polling (only when ENABLE_DESCRIBE=1 and docs are still describing) ─
let pollTimer: ReturnType<typeof setInterval> | null = null

const hasDescribing = computed(() =>
  store.documents.some((d) => d.status === 'describing'),
)

function startPollingIfNeeded() {
  if (pollTimer !== null || !hasDescribing.value) return
  pollTimer = setInterval(async () => {
    await store.loadAll()
    if (!hasDescribing.value) stopPolling()
  }, 3000)
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// Delay the skeleton so fast loads (local SQLite) don't flash grey rows.
const showSkeleton = ref(false)

onMounted(async () => {
  const skeletonTimer = setTimeout(() => {
    showSkeleton.value = true
  }, 200)
  await store.loadAll()
  clearTimeout(skeletonTimer)
  showSkeleton.value = false
  startPollingIfNeeded()
})
onUnmounted(stopPolling)

// ── Helpers ────────────────────────────────────────────────────────────────────
function humanSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

function downloadUrl(id: string) {
  return apiUrl(`/api/documents/${id}/raw`)
}
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="shrink-0 h-16 border-b px-8 flex flex-col justify-center">
      <h1 class="text-xl font-semibold tracking-tight">Documents</h1>
      <p class="text-sm text-muted-foreground mt-0.5">Upload files — bytes in a DSS Managed Folder, metadata in SQLite.</p>
    </header>
    <div class="flex-1 overflow-auto">
    <div class="max-w-5xl mx-auto p-8 space-y-6">

      <!-- Upload dropzone -->
      <div
        class="border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer"
        :class="isDragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'"
        @click="fileInputRef?.click()"
        @dragover.prevent="isDragging = true"
        @dragleave="isDragging = false"
        @drop.prevent="onDrop"
      >
        <input ref="fileInputRef" type="file" multiple class="hidden" @change="onFileInput" />
        <Upload class="w-8 h-8 mx-auto mb-2 text-muted-foreground" />
        <p class="text-sm font-medium">Drop files here or click to browse</p>
        <p class="text-xs text-muted-foreground mt-1">
          PDF, images, audio, video, and text/code files
        </p>
        <Loader2 v-if="uploading" class="w-4 h-4 mx-auto mt-2 animate-spin text-muted-foreground" />
      </div>

      <p v-if="uploadError" class="text-sm text-destructive">{{ uploadError }}</p>

      <!-- Document list -->
      <div v-if="showSkeleton && !store.documents.length" class="space-y-2">
        <div v-for="i in 3" :key="i" class="h-12 bg-muted animate-pulse rounded-lg" />
      </div>

      <!-- Backend error (most likely: DSS Managed Folder not yet configured) -->
      <EaEmpty
        v-else-if="store.error && !store.documents.length"
        :icon="AlertTriangle"
        title="Documents not available"
        description="Could not reach the Documents backend. Make sure ENABLE_DOCUMENTS=1 is set and a DSS Managed Folder is accessible — see README 'Optional building blocks'."
      />

      <EaEmpty
        v-else-if="!store.documents.length"
        :icon="FileText"
        title="No documents yet"
        description="Upload files above to get started."
      />

      <div v-else class="border rounded-lg overflow-hidden">
        <!-- Table header -->
        <div class="px-4 py-2.5 border-b bg-muted/30 grid grid-cols-[1fr_auto_auto_auto] gap-4 items-center">
          <span class="text-xs font-medium text-muted-foreground uppercase tracking-wide">File</span>
          <span class="text-xs font-medium text-muted-foreground uppercase tracking-wide w-20 text-right">Size</span>
          <span class="text-xs font-medium text-muted-foreground uppercase tracking-wide w-24">Status</span>
          <span class="w-20" />
        </div>

        <!-- Rows -->
        <div
          v-for="doc in store.documents"
          :key="doc.id"
          class="px-4 py-3 border-b last:border-0 hover:bg-muted/10 transition-colors"
        >
          <!-- Main row -->
          <div class="grid grid-cols-[1fr_auto_auto_auto] gap-4 items-center">
            <!-- Filename / inline rename -->
            <div class="min-w-0">
              <template v-if="renamingId === doc.id">
                <div class="flex items-center gap-2">
                  <input
                    v-model="renameValue"
                    class="flex-1 text-sm border rounded px-2 py-1 bg-background"
                    @keydown.enter="commitRename(doc.id)"
                    @keydown.escape="renamingId = null"
                    autofocus
                  />
                  <button
                    class="text-xs text-primary hover:underline"
                    @click="commitRename(doc.id)"
                  >Save</button>
                  <button
                    class="text-xs text-muted-foreground hover:underline"
                    @click="renamingId = null"
                  >Cancel</button>
                </div>
                <p v-if="renameError" class="text-xs text-destructive mt-1">{{ renameError }}</p>
              </template>
              <span v-else class="text-sm font-medium truncate block" :title="doc.filename">
                {{ doc.filename }}
              </span>
              <!-- Description (shown when available) -->
              <p
                v-if="doc.description"
                class="text-xs text-muted-foreground mt-0.5 line-clamp-2"
              >
                {{ doc.description }}
              </p>
              <p v-if="doc.error" class="text-xs text-destructive mt-0.5">{{ doc.error }}</p>
            </div>

            <!-- Size -->
            <span class="text-xs text-muted-foreground w-20 text-right tabular-nums">
              {{ humanSize(doc.size_bytes) }}
            </span>

            <!-- Status badge -->
            <div class="w-24 flex items-center gap-1">
              <Loader2
                v-if="doc.status === 'describing'"
                class="w-3.5 h-3.5 animate-spin text-muted-foreground"
              />
              <CheckCircle2
                v-else-if="doc.status === 'ready'"
                class="w-3.5 h-3.5 text-green-500"
              />
              <AlertTriangle
                v-else
                class="w-3.5 h-3.5 text-destructive"
              />
              <span class="text-xs text-muted-foreground capitalize">{{ doc.status }}</span>
            </div>

            <!-- Actions -->
            <div class="w-20 flex items-center justify-end gap-1">
              <a
                :href="downloadUrl(doc.id)"
                download
                class="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                title="Download"
              >
                <Download class="w-3.5 h-3.5" />
              </a>
              <button
                class="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                title="Rename"
                @click="startRename(doc)"
              >
                <Pencil class="w-3.5 h-3.5" />
              </button>
              <button
                class="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                title="Re-describe"
                @click="redescribe(doc.id)"
              >
                <RefreshCw class="w-3.5 h-3.5" />
              </button>
              <button
                class="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-destructive transition-colors"
                :class="{ 'opacity-50': deletingId === doc.id }"
                title="Delete"
                :disabled="deletingId === doc.id"
                @click="confirmDelete(doc.id)"
              >
                <Trash2 v-if="deletingId !== doc.id" class="w-3.5 h-3.5" />
                <Loader2 v-else class="w-3.5 h-3.5 animate-spin" />
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
    </div>
  </div>
</template>

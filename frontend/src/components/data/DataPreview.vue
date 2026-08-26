<script setup lang="ts">
  import { Binary, CaseSensitive, ChevronsUpDown } from 'lucide-vue-next'
  import Table from '@/components/ui/table/Table.vue'
  import TableBody from '@/components/ui/table/TableBody.vue'
  import TableCell from '@/components/ui/table/TableCell.vue'
  import TableHead from '@/components/ui/table/TableHead.vue'
  import TableHeader from '@/components/ui/table/TableHeader.vue'
  import TableRow from '@/components/ui/table/TableRow.vue'
  import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'

  interface DataPreviewProps {
    rows: Record<string, unknown>[]
    columns: string[]
    schema: Record<string, string>
    error?: string | null
  }

  const props = defineProps<DataPreviewProps>()

  const emit = defineEmits<{
    (event: 'sort', column: string): void
  }>()
</script>

<template>
  <div class="flex flex-col w-full overflow-x-auto">
    <!-- Error state -->
    <p
      v-if="props.error"
      class="text-sm text-destructive px-1 py-4"
    >
      {{ props.error }}
    </p>

    <!-- Empty state -->
    <div
      v-else-if="!props.rows.length"
      class="text-center py-8 text-sm text-muted-foreground"
    >
      No data to display.
    </div>

    <!-- Table -->
    <div v-else>
      <ScrollArea>
        <div class="w-full overflow-x-auto border border-border rounded-md">
          <Table
            class="min-w-full text-sm text-foreground [&_th]:px-4 [&_td]:px-4 [&_td]:py-2 [&_th]:py-2 [&_th]:text-foreground [&_td]:text-foreground"
          >
            <TableHeader class="w-full">
              <TableRow class="bg-background">
                <!-- Row-number column -->
                <TableHead class="w-6 bg-background border-r border-border">
                  #
                </TableHead>
                <!-- Data columns -->
                <TableHead
                  v-for="column in props.columns"
                  :key="column"
                  class="font-semibold border-0 cursor-pointer select-none text-muted-foreground"
                  @click="emit('sort', column)"
                >
                  <div>
                    <div class="flex items-center gap-1">
                      <component
                        :is="props.schema?.[column] === 'string' ? CaseSensitive : Binary"
                        class="inline w-3 h-3 text-muted-foreground mr-1"
                      />
                      {{ column }}
                      <ChevronsUpDown
                        class="w-4 h-4 font-semibold ml-3"
                        :stroke-width="2.2"
                      />
                    </div>
                    <div class="text-xs text-muted-foreground font-normal ml-5 mt-1">
                      <i>{{ props.schema?.[column] }}</i>
                    </div>
                  </div>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                v-for="(row, index) in props.rows"
                :key="index"
                class="hover:bg-muted/20"
              >
                <!-- Row number -->
                <TableCell class="w-6 bg-background border-r border-border text-xs">
                  <span class="text-muted-foreground font-normal block">
                    {{ index + 1 }}
                  </span>
                </TableCell>
                <!-- Data cells -->
                <TableCell
                  v-for="column in props.columns"
                  :key="column"
                  class="text-xs"
                >
                  <span
                    class="truncate block max-w-[200px] ml-4"
                    :title="String(row[column] ?? '')"
                  >
                    {{ row[column] ?? '—' }}
                  </span>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <ScrollBar orientation="horizontal" />
        </div>
      </ScrollArea>
    </div>
  </div>
</template>

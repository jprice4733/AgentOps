export type SortDirection = 'asc' | 'desc'

export interface SortState {
  column: string
  direction: SortDirection
}

export type NullStrategy = 'always-last' | 'ascending-first'

interface SortOptions {
  nullStrategy?: NullStrategy
  caseInsensitive?: boolean
}

export function getNextSortState(current: SortState | null, column: string): SortState {
  if (current?.column === column) {
    return {
      column,
      direction: current.direction === 'asc' ? 'desc' : 'asc',
    }
  }

  return {
    column,
    direction: 'asc',
  }
}

export function sortRows<T extends Record<string, unknown>>(
  rows: T[],
  state: SortState | null,
  options: SortOptions = {},
): T[] {
  if (!state) {
    return [...rows]
  }

  const { column, direction } = state
  const { nullStrategy = 'always-last', caseInsensitive = false } = options
  const factor = direction === 'asc' ? 1 : -1

  return [...rows].sort((a, b) => {
    const aVal = a[column]
    const bVal = b[column]

    if (aVal == null && bVal == null) return 0

    if (aVal == null) {
      if (nullStrategy === 'ascending-first' && direction === 'asc') {
        return -1
      }
      return 1
    }

    if (bVal == null) {
      if (nullStrategy === 'ascending-first' && direction === 'asc') {
        return 1
      }
      return -1
    }

    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return factor * (aVal - bVal)
    }

    const aStr = String(aVal)
    const bStr = String(bVal)

    if (caseInsensitive) {
      return factor * aStr.localeCompare(bStr, undefined, { sensitivity: 'base' })
    }

    return factor * aStr.localeCompare(bStr)
  })
}

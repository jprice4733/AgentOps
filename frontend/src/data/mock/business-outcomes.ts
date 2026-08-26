// Mock data powering the business-outcome dashboard on the Charts tab.
// Numbers are hand-tuned so the story stays internally consistent:
//   connected sources × event rate ≈ timeline totals
//   auto-resolved + assisted ≈ automation rate × total events
//   weekly savings summed across 12 weeks ≈ quarter savings KPI

export type DeltaDirection = 'up' | 'down' | 'flat'

export interface KpiValue {
  label: string
  value: string
  deltaLabel: string
  deltaDirection: DeltaDirection
  // true when "up" is good (e.g. savings); false when "up" is bad (e.g. open items).
  upIsGood: boolean
  sparkline: number[]
  caption?: string
}

export interface AlertsTimelinePoint {
  date: string
  agentResolved: number
  humanEscalated: number
}

export interface ResolutionMixSlice {
  label: string
  value: number
}

export interface TopActivity {
  name: string
  info: number
  warning: number
  critical: number
}

export interface WeeklySavings {
  week: string
  savings: number
}

// Deterministic PRNG so the dashboard renders the same numbers every reload.
function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5)
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function buildAlertsTimeline(): AlertsTimelinePoint[] {
  const rng = mulberry32(42)
  const points: AlertsTimelinePoint[] = []
  const today = new Date('2026-04-15')
  for (let i = 89; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(today.getDate() - i)
    // Baseline rises slightly over the quarter (more sources connected over time).
    const baseline = 2 + (89 - i) * 0.03
    // Weekly seasonality — weekends dip.
    const dow = d.getDay()
    const weekend = dow === 0 || dow === 6 ? 0.6 : 1
    const agent = Math.max(0, Math.round((baseline + rng() * 4) * weekend))
    const escalated = Math.max(0, Math.round((0.3 + rng() * 1.2) * weekend))
    points.push({
      date: d.toISOString().slice(0, 10),
      agentResolved: agent,
      humanEscalated: escalated,
    })
  }
  return points
}

function buildSparkline(seed: number, length = 14, min = 30, max = 90): number[] {
  const rng = mulberry32(seed)
  return Array.from({ length }, () => Math.round(min + rng() * (max - min)))
}

export const alertsTimeline: AlertsTimelinePoint[] = buildAlertsTimeline()

const totalAgent = alertsTimeline.reduce((s, p) => s + p.agentResolved, 0)
const totalEscalated = alertsTimeline.reduce((s, p) => s + p.humanEscalated, 0)
const totalAlerts = totalAgent + totalEscalated

export const kpis: Record<string, KpiValue> = {
  connectedActivities: {
    label: 'Connected sources',
    value: '14',
    deltaLabel: '+2 this quarter',
    deltaDirection: 'up',
    upIsGood: true,
    sparkline: [8, 8, 9, 9, 10, 10, 11, 12, 12, 13, 13, 13, 14, 14],
    caption: 'Data sources feeding the pipeline',
  },
  alertsManagedPct: {
    label: 'Handled automatically',
    value: '87%',
    deltaLabel: '+6 pts vs. prev. 90 d',
    deltaDirection: 'up',
    upIsGood: true,
    sparkline: buildSparkline(11, 14, 74, 90),
    caption: 'Completed without manual intervention',
  },
  openAlerts: {
    label: 'Open items',
    value: '3',
    deltaLabel: '−4 vs. last week',
    deltaDirection: 'down',
    upIsGood: false,
    sparkline: buildSparkline(17, 14, 2, 11).map((v, i, arr) => (i === arr.length - 1 ? 3 : v)),
    caption: 'Awaiting manual review',
  },
  quarterSavings: {
    label: 'Estimated savings this quarter',
    value: '$412k',
    deltaLabel: '+18% vs. prev. quarter',
    deltaDirection: 'up',
    upIsGood: true,
    sparkline: buildSparkline(23, 14, 40, 85),
    caption: 'Manual effort and rework avoided',
  },
}

export const resolutionMix: ResolutionMixSlice[] = [
  { label: 'Auto-resolved', value: Math.round(totalAgent * 0.82) },
  { label: 'Assisted', value: Math.round(totalAgent * 0.18) },
  { label: 'Manual', value: totalEscalated },
  { label: 'False positives', value: Math.round(totalAlerts * 0.05) },
]

export const topActivities: TopActivity[] = [
  { name: 'Orders · validation', info: 42, warning: 18, critical: 4 },
  { name: 'Payments · fraud check', info: 36, warning: 15, critical: 3 },
  { name: 'Invoices · matching', info: 31, warning: 12, critical: 2 },
  { name: 'Tickets · triage', info: 28, warning: 9, critical: 2 },
  { name: 'Shipments · tracking', info: 24, warning: 8, critical: 1 },
  { name: 'Returns · processing', info: 19, warning: 6, critical: 1 },
  { name: 'Accounts · verification', info: 16, warning: 5, critical: 0 },
  { name: 'Refunds · approval', info: 12, warning: 3, critical: 1 },
]

export const weeklySavings: WeeklySavings[] = (() => {
  const rng = mulberry32(101)
  const target = 412
  const base = Array.from({ length: 12 }, () => 22 + rng() * 20)
  const sum = base.reduce((s, v) => s + v, 0)
  const scale = target / sum
  return base.map((v, i) => ({
    week: `W${i + 1}`,
    savings: Math.round(v * scale * 1000),
  }))
})()

export const automationRate = 87

export const timeWindowLabel = 'Last 90 days'

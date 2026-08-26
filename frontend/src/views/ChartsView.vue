<script setup lang="ts">
/**
 * ChartsView — business-impact dashboard.
 *
 * Renders a self-contained mock dashboard: 4 KPI cards with sparklines,
 * a stacked area timeline, a resolution donut, a horizontal stacked bar,
 * a weekly-savings bar, and an automation gauge.
 *
 * All data comes from the local mock-data file (frontend/src/data/mock/
 * business-outcomes.ts) — no backend call, no store. Replace the mock
 * exports with real DSS dataset reads when productionising.
 *
 * Enabled when ENABLE_CHARTS=1 in app.env.
 */
import { Activity, Bot, AlertTriangle, DollarSign } from 'lucide-vue-next'
import KpiCard from '@/components/dashboard/KpiCard.vue'
import AlertsTimelineChart from '@/components/dashboard/AlertsTimelineChart.vue'
import ResolutionMixDonut from '@/components/dashboard/ResolutionMixDonut.vue'
import TopActivitiesBarChart from '@/components/dashboard/TopActivitiesBarChart.vue'
import WeeklySavingsChart from '@/components/dashboard/WeeklySavingsChart.vue'
import AutomationGauge from '@/components/dashboard/AutomationGauge.vue'
import {
  kpis,
  alertsTimeline,
  resolutionMix,
  topActivities,
  weeklySavings,
  automationRate,
  timeWindowLabel,
} from '@/data/mock/business-outcomes'

defineOptions({ name: 'ChartsView' })
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="shrink-0 h-16 border-b px-8 flex items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight">Business impact</h1>
        <p class="text-sm text-muted-foreground mt-0.5">How your automation is performing — {{ timeWindowLabel.toLowerCase() }}.</p>
      </div>
      <span
        class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white border text-xs font-medium text-muted-foreground shrink-0"
      >
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500" />
        {{ timeWindowLabel }}
      </span>
    </header>
    <div class="flex-1 overflow-y-auto bg-muted/30">
    <div class="max-w-[1400px] mx-auto p-8 space-y-6">

      <!-- KPI row -->
      <section class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard :kpi="kpis.connectedActivities" :icon="Activity" accent="hsl(233.92 50% 35%)" />
        <KpiCard :kpi="kpis.alertsManagedPct" :icon="Bot" accent="hsl(172, 46%, 48%)" />
        <KpiCard :kpi="kpis.openAlerts" :icon="AlertTriangle" accent="hsl(0, 78%, 58%)" />
        <KpiCard :kpi="kpis.quarterSavings" :icon="DollarSign" accent="hsl(172, 46%, 48%)" />
      </section>

      <!-- Chart row 1: timeline + donut -->
      <section class="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <article class="lg:col-span-8 rounded-xl border bg-white p-5 flex flex-col">
          <header class="mb-3">
            <h2 class="text-base font-semibold">Events over time</h2>
            <p class="text-xs text-muted-foreground mt-0.5">
              Daily volume, split by how each was handled.
            </p>
          </header>
          <div class="flex-1 min-h-[300px]">
            <AlertsTimelineChart :data="alertsTimeline" />
          </div>
        </article>

        <article class="lg:col-span-4 rounded-xl border bg-white p-5 flex flex-col">
          <header class="mb-3">
            <h2 class="text-base font-semibold">Resolution mix</h2>
            <p class="text-xs text-muted-foreground mt-0.5">
              How items were resolved across {{ timeWindowLabel.toLowerCase() }}.
            </p>
          </header>
          <div class="flex-1 min-h-[300px]">
            <ResolutionMixDonut :data="resolutionMix" />
          </div>
        </article>
      </section>

      <!-- Chart row 2: top sources + weekly savings -->
      <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <article class="rounded-xl border bg-white p-5 flex flex-col">
          <header class="mb-3">
            <h2 class="text-base font-semibold">Top sources by volume</h2>
            <p class="text-xs text-muted-foreground mt-0.5">
              Where automation is handling the most work.
            </p>
          </header>
          <div class="flex-1 min-h-[320px]">
            <TopActivitiesBarChart :data="topActivities" />
          </div>
        </article>

        <article class="rounded-xl border bg-white p-5 flex flex-col">
          <header class="mb-3">
            <h2 class="text-base font-semibold">Estimated weekly savings</h2>
            <p class="text-xs text-muted-foreground mt-0.5">
              Manual effort avoided, last 12 weeks.
            </p>
          </header>
          <div class="flex-1 min-h-[320px]">
            <WeeklySavingsChart :data="weeklySavings" />
          </div>
        </article>
      </section>

      <!-- Gauge row -->
      <section class="rounded-xl border bg-white p-5">
        <div class="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
          <div class="md:col-span-4 h-[220px]">
            <AutomationGauge :value="automationRate" />
          </div>
          <div class="md:col-span-8 space-y-3">
            <h2 class="text-lg font-semibold">Automation rate</h2>
            <p class="text-sm text-muted-foreground leading-relaxed">
              {{ automationRate }}% of items were processed end-to-end automatically
              with no manual intervention required. The remaining {{ 100 - automationRate }}%
              were escalated for review or manual handling.
            </p>
            <div class="flex gap-6 pt-2">
              <div>
                <p class="text-xs text-muted-foreground uppercase tracking-wide">Target</p>
                <p class="text-lg font-semibold mt-1">80%</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground uppercase tracking-wide">Previous quarter</p>
                <p class="text-lg font-semibold mt-1">81%</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground uppercase tracking-wide">Trend</p>
                <p class="text-lg font-semibold mt-1 text-emerald-600">+6 pts</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
    </div>
  </div>
</template>

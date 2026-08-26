<script setup lang="ts">
  import { computed, nextTick, onMounted, ref } from 'vue';
  import VChart from 'vue-echarts';
  import { use } from 'echarts/core';
  import { LineChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import type { EChartsOption } from 'echarts';
  import type { AlertsTimelinePoint } from '@/data/mock/business-outcomes';

  use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

  const props = defineProps<{ data: AlertsTimelinePoint[] }>();

  const ready = ref(false);
  onMounted(() => nextTick(() => (ready.value = true)));

  const AUTOMATED_COLOR = 'hsl(172, 46%, 48%)';
  const ESCALATED_COLOR = 'hsl(233.92, 50%, 35%)';

  const chartOption = computed((): EChartsOption => ({
    animationDuration: 900,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: 'hsl(240, 6%, 80%)' } },
    },
    legend: {
      data: ['Automated', 'Escalated'],
      bottom: 0,
      textStyle: { fontSize: 12, color: 'hsl(240, 3.8%, 46.1%)' },
      itemWidth: 10,
      itemHeight: 10,
      icon: 'roundRect',
    },
    grid: { left: 40, right: 16, top: 16, bottom: 44 },
    xAxis: {
      type: 'category',
      data: props.data.map((d) => d.date),
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: 'hsl(240, 6%, 90%)' } },
      axisLabel: {
        color: 'hsl(240, 3.8%, 46.1%)',
        fontSize: 10,
        formatter: (v: string) => {
          const d = new Date(v);
          return `${d.toLocaleString('en-US', { month: 'short' })} ${d.getDate()}`;
        },
        interval: Math.floor(props.data.length / 6),
      },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { type: 'dashed', color: 'hsl(240, 6%, 92%)' } },
      axisLabel: { color: 'hsl(240, 3.8%, 46.1%)', fontSize: 10 },
    },
    series: [
      {
        name: 'Automated',
        type: 'line',
        stack: 'alerts',
        data: props.data.map((d) => d.agentResolved),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: AUTOMATED_COLOR },
        itemStyle: { color: AUTOMATED_COLOR },
        areaStyle: { color: AUTOMATED_COLOR, opacity: 0.2 },
      },
      {
        name: 'Escalated',
        type: 'line',
        stack: 'alerts',
        data: props.data.map((d) => d.humanEscalated),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: ESCALATED_COLOR },
        itemStyle: { color: ESCALATED_COLOR },
        areaStyle: { color: ESCALATED_COLOR, opacity: 0.2 },
      },
    ],
  }));
</script>

<template>
  <div class="h-full w-full">
    <VChart
      v-if="ready"
      :option="chartOption"
      :autoresize="true"
      class="h-full w-full"
    />
  </div>
</template>

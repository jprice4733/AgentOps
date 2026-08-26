<script setup lang="ts">
  import { computed, nextTick, onMounted, ref } from 'vue';
  import VChart from 'vue-echarts';
  import { use } from 'echarts/core';
  import { BarChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import type { EChartsOption } from 'echarts';
  import type { WeeklySavings } from '@/data/mock/business-outcomes';

  use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

  const props = defineProps<{ data: WeeklySavings[] }>();

  const ready = ref(false);
  onMounted(() => nextTick(() => (ready.value = true)));

  const BAR_COLOR = 'hsl(172, 46%, 48%)';

  function formatDollars(v: number): string {
    if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`;
    return `$${v}`;
  }

  const chartOption = computed((): EChartsOption => ({
    animationDuration: 900,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (v) => formatDollars(Number(v)),
    },
    grid: { left: 46, right: 12, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: props.data.map((d) => d.week),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: 'hsl(240, 6%, 90%)' } },
      axisLabel: { color: 'hsl(240, 3.8%, 46.1%)', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { type: 'dashed', color: 'hsl(240, 6%, 92%)' } },
      axisLabel: {
        color: 'hsl(240, 3.8%, 46.1%)',
        fontSize: 10,
        formatter: (v: number) => formatDollars(v),
      },
    },
    series: [
      {
        type: 'bar',
        data: props.data.map((d) => d.savings),
        itemStyle: {
          color: BAR_COLOR,
          borderRadius: [4, 4, 0, 0],
        },
        barWidth: 18,
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

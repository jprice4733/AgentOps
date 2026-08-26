<script setup lang="ts">
  import { computed, nextTick, onMounted, ref } from 'vue';
  import VChart from 'vue-echarts';
  import { use } from 'echarts/core';
  import { BarChart } from 'echarts/charts';
  import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import type { EChartsOption } from 'echarts';
  import type { TopActivity } from '@/data/mock/business-outcomes';

  use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

  const props = defineProps<{ data: TopActivity[] }>();

  const ready = ref(false);
  onMounted(() => nextTick(() => (ready.value = true)));

  const COLORS = {
    info: 'hsl(172, 46%, 68%)',
    warning: 'hsl(40, 90%, 55%)',
    critical: 'hsl(0, 78%, 58%)',
  };

  // Sort ascending so the biggest bar ends up at the top (ECharts Y axis
  // renders the first category at the bottom by default).
  const sorted = computed(() =>
    [...props.data].sort(
      (a, b) => a.info + a.warning + a.critical - (b.info + b.warning + b.critical),
    ),
  );

  const chartOption = computed((): EChartsOption => ({
    animationDuration: 900,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    legend: {
      data: ['Info', 'Warning', 'Critical'],
      bottom: 0,
      itemWidth: 10,
      itemHeight: 10,
      icon: 'roundRect',
      textStyle: { fontSize: 12, color: 'hsl(240, 3.8%, 46.1%)' },
    },
    grid: { left: 0, right: 16, top: 8, bottom: 36, containLabel: true },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { type: 'dashed', color: 'hsl(240, 6%, 92%)' } },
      axisLabel: { color: 'hsl(240, 3.8%, 46.1%)', fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      data: sorted.value.map((a) => a.name),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: 'hsl(240, 3.8%, 30%)', fontSize: 11 },
    },
    series: [
      {
        name: 'Info',
        type: 'bar',
        stack: 'alerts',
        data: sorted.value.map((a) => a.info),
        itemStyle: { color: COLORS.info, borderRadius: [0, 0, 0, 0] },
        barWidth: 18,
      },
      {
        name: 'Warning',
        type: 'bar',
        stack: 'alerts',
        data: sorted.value.map((a) => a.warning),
        itemStyle: { color: COLORS.warning },
      },
      {
        name: 'Critical',
        type: 'bar',
        stack: 'alerts',
        data: sorted.value.map((a) => a.critical),
        itemStyle: { color: COLORS.critical, borderRadius: [0, 4, 4, 0] },
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

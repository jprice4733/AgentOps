<script setup lang="ts">
  import { computed, nextTick, onMounted, ref } from 'vue';
  import VChart from 'vue-echarts';
  import { use } from 'echarts/core';
  import { GaugeChart } from 'echarts/charts';
  import { CanvasRenderer } from 'echarts/renderers';
  import type { EChartsOption } from 'echarts';

  use([GaugeChart, CanvasRenderer]);

  const props = defineProps<{ value: number }>();

  const ready = ref(false);
  onMounted(() => nextTick(() => (ready.value = true)));

  const chartOption = computed((): EChartsOption => ({
    animationDuration: 1200,
    animationEasing: 'cubicOut',
    series: [
      {
        type: 'gauge',
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        radius: '100%',
        center: ['50%', '62%'],
        progress: { show: false },
        axisLine: {
          lineStyle: {
            width: 14,
            color: [
              [0.6, 'hsl(0, 78%, 58%)'],
              [0.8, 'hsl(40, 90%, 55%)'],
              [1, 'hsl(172, 46%, 48%)'],
            ],
          },
        },
        pointer: {
          length: '65%',
          width: 5,
          itemStyle: { color: 'hsl(233.92, 50%, 35%)' },
        },
        axisTick: {
          distance: -18,
          length: 4,
          lineStyle: { color: '#fff', width: 1 },
        },
        splitLine: {
          distance: -18,
          length: 12,
          lineStyle: { color: '#fff', width: 2 },
        },
        axisLabel: {
          distance: -30,
          fontSize: 10,
          color: 'hsl(240, 3.8%, 46.1%)',
          formatter: (v: number) => `${v}`,
        },
        anchor: {
          show: true,
          size: 10,
          itemStyle: {
            borderWidth: 4,
            borderColor: 'hsl(233.92, 50%, 35%)',
            color: '#fff',
          },
        },
        detail: {
          valueAnimation: true,
          formatter: (v: number) => `${Math.round(v)}%`,
          fontSize: 30,
          fontWeight: 600,
          color: 'hsl(240 10% 3.9%)',
          offsetCenter: [0, '38%'],
        },
        data: [{ value: props.value }],
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

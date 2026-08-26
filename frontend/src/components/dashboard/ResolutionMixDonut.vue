<script setup lang="ts">
  import { computed, nextTick, onMounted, ref } from 'vue';
  import VChart from 'vue-echarts';
  import { use } from 'echarts/core';
  import { PieChart } from 'echarts/charts';
  import { TooltipComponent, LegendComponent } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import type { EChartsOption } from 'echarts';
  import type { ResolutionMixSlice } from '@/data/mock/business-outcomes';

  use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer]);

  const props = defineProps<{ data: ResolutionMixSlice[] }>();

  const ready = ref(false);
  onMounted(() => nextTick(() => (ready.value = true)));

  const COLORS = [
    'hsl(172, 46%, 48%)',
    'hsl(172, 46%, 68%)',
    'hsl(233.92, 50%, 35%)',
    'hsl(240, 5%, 75%)',
  ];

  const chartOption = computed((): EChartsOption => ({
    animationDuration: 900,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      orient: 'vertical',
      right: 0,
      top: 'center',
      itemWidth: 10,
      itemHeight: 10,
      icon: 'roundRect',
      textStyle: { fontSize: 12, color: 'hsl(240, 3.8%, 30%)' },
    },
    series: [
      {
        type: 'pie',
        radius: ['58%', '82%'],
        center: ['32%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: { show: false },
        labelLine: { show: false },
        data: props.data.map((d, i) => ({
          name: d.label,
          value: d.value,
          itemStyle: { color: COLORS[i % COLORS.length] },
        })),
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

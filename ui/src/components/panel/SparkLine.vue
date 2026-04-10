<script setup lang="ts">
import { computed } from 'vue';
import * as d3 from 'd3';

export interface SparkDataPoint {
  time: Date;
  value: number | null;
}

const props = withDefaults(
  defineProps<{
    col: number;
    row: number;
    colSpan?: number;
    rowSpan?: number;
    data: SparkDataPoint[];
    yMin?: number;
    yMax?: number;
    reference?: number;
    color?: string;
  }>(),
  {
    colSpan: 1,
    rowSpan: 1,
    yMin: undefined,
    yMax: undefined,
    reference: undefined,
    color: '#ffffff',
  }
);

// Fixed logical coordinate space; SVG stretches to fill the cell.
const W = 100;
const H = 50;

const gridStyle = computed(() => ({
  gridColumn: `${props.col} / span ${props.colSpan}`,
  gridRow: `${props.row} / span ${props.rowSpan}`,
}));

const validPoints = computed(() => props.data.filter((d) => d.value !== null));

const xScale = computed(() => {
  const times = validPoints.value.map((d) => d.time);
  const [t0, t1] = d3.extent(times) as [Date | undefined, Date | undefined];
  const now = new Date();
  return d3
    .scaleTime()
    .domain([t0 ?? now, t1 ?? now])
    .range([0, W]);
});

const yScale = computed(() => {
  if (props.yMin != null && props.yMax != null) {
    return d3
      .scaleLinear()
      .domain([props.yMin, props.yMax])
      .range([H, 0])
      .clamp(true);
  }
  const vals = validPoints.value.map((d) => d.value as number);
  const [mn, mx] = d3.extent(vals) as [number | undefined, number | undefined];
  const pad = mn != null && mx != null ? Math.max((mx - mn) * 0.1, 1) : 5;
  return d3
    .scaleLinear()
    .domain([mn != null ? mn - pad : 0, mx != null ? mx + pad : 100])
    .range([H, 0]);
});

const pathD = computed(() => {
  const line = d3
    .line<SparkDataPoint>()
    .defined((d) => d.value !== null)
    .x((d) => xScale.value(d.time))
    .y((d) => yScale.value(d.value as number))
    .curve(d3.curveMonotoneX);
  return line(props.data) ?? '';
});

const referenceY = computed(() =>
  props.reference != null ? yScale.value(props.reference) : null
);
</script>

<template>
  <div :style="gridStyle" class="sparkline">
    <svg
      width="100%"
      height="100%"
      :viewBox="`0 0 ${W} ${H}`"
      preserveAspectRatio="none"
    >
      <line
        v-if="referenceY !== null"
        x1="0"
        :y1="referenceY"
        :x2="W"
        :y2="referenceY"
        stroke="#555"
        stroke-width="1"
        vector-effect="non-scaling-stroke"
      />
      <path
        v-if="pathD"
        :d="pathD"
        fill="none"
        :stroke="color"
        stroke-width="1.5"
        stroke-linejoin="round"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
      />
    </svg>
  </div>
</template>

<style scoped lang="scss">
.sparkline {
  overflow: hidden;
  box-sizing: border-box;
  background: var(--panel-control-bg, #000000);
}
</style>

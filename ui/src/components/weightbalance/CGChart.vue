<script setup lang="ts">
// Reusable CG envelope chart: inches on X, weight on Y, in the same
// hand-rolled SVG + d3-scale style as LineGraph.vue (no chart library).
// Purely presentational + an svgString() export for the save snapshot —
// all it needs is a Layout (for the envelope/limit lines) and the
// already-computed curve/markers from useWeightBalanceCalc, so it has no
// fetch/router dependency and can be reused by a future panel calculator.
import { computed, onMounted, onUnmounted, ref } from 'vue';
import * as d3 from 'd3';
import type { Layout } from '@/types/weightbalance';
import type { WeightBalanceCalc } from '@/composables/useWeightBalanceCalc';

const props = defineProps<{
  layout: Layout;
  calc: WeightBalanceCalc;
}>();

const containerRef = ref<HTMLDivElement | null>(null);
const containerWidth = ref(400);
const height = 320;
// The X/Y scales themselves are tight around the actual data (no extra
// domain padding) -- top/right are sized instead as fixed pixel gutters,
// just enough to keep a marker dot/label sitting exactly at the top or
// right edge of the data (e.g. FFW) from being clipped. left/bottom are
// sized for the axis tick labels, unrelated to this.
const margin = { top: 22, right: 34, bottom: 34, left: 56 };

const innerWidth = computed(() =>
  Math.max(0, containerWidth.value - margin.left - margin.right)
);
const innerHeight = computed(() => height - margin.top - margin.bottom);

onMounted(() => {
  if (!containerRef.value) {
    return;
  }
  containerWidth.value = containerRef.value.clientWidth;
  const ro = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (entry) {
      containerWidth.value = entry.contentRect.width;
    }
  });
  ro.observe(containerRef.value);
  onUnmounted(() => ro.disconnect());
});

// X domain: tight around every CG limit point plus the curve (which
// includes the full FFW→ZFW line) -- no extra domain padding. Room for
// marker labels/dots sitting right at the edges comes from the fixed
// margin.right gutter above, not from padding the data itself.
const xScale = computed(() => {
  const cgs = [
    ...props.layout.forwardCGLimits.map((p) => p.cg),
    ...props.layout.aftCGLimits.map((p) => p.cg),
    ...props.calc.curve.map((p) => p.cg),
  ];
  const [lo, hi] = d3.extent(cgs) as [number | undefined, number | undefined];
  const min = lo ?? 0;
  const max = hi ?? 1;
  // A degenerate (zero-width) domain would otherwise map every point to the
  // same pixel; give it a minimal span in that edge case only.
  const span = max > min ? 0 : 0.5;
  return d3
    .scaleLinear()
    .domain([min - span, max + span])
    .range([0, innerWidth.value]);
});

// Y domain: from the basic empty weight (the floor -- nothing on the chart
// is ever lighter than the bare airplane) up to the largest weight in play
// (limits, MTOW/MLW/MZFW, curve) -- no extra domain padding; margin.top
// above reserves the pixel space a top-edge marker's label needs.
const yScale = computed(() => {
  const weights = [
    ...props.layout.forwardCGLimits.map((p) => p.weight),
    ...props.layout.aftCGLimits.map((p) => p.weight),
    ...props.calc.curve.map((p) => p.weight),
    props.layout.maxTakeoffWeight,
    props.layout.maxLandingWeight,
    props.layout.maxZeroFuelWeight,
  ].filter((w) => w > 0);
  const max = d3.max(weights) ?? props.layout.emptyWeight + 100;
  return d3
    .scaleLinear()
    .domain([props.layout.emptyWeight, max])
    .range([innerHeight.value, 0]);
});

// Envelope polygon: forward limits ascending by weight (left boundary), then
// aft limits descending by weight (right boundary), closing the loop.
const envelopePath = computed(() => {
  const fwd = [...props.layout.forwardCGLimits].sort(
    (a, b) => a.weight - b.weight
  );
  const aft = [...props.layout.aftCGLimits]
    .sort((a, b) => a.weight - b.weight)
    .reverse();
  const pts = [...fwd, ...aft];
  if (pts.length < 3) {
    return '';
  }
  const x = xScale.value;
  const y = yScale.value;
  return (
    pts
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(p.cg)} ${y(p.weight)}`)
      .join(' ') + ' Z'
  );
});

// The curve is split at TOW: ZFW→TOW is the actual flown portion (solid);
// TOW→FFW is "what if the tanks were fuller" and never actually flown
// (dotted). TOW's own point is included in both halves so they connect
// without a visible gap.
const flownCurvePath = computed(() => {
  const x = xScale.value;
  const y = yScale.value;
  const towGal = props.calc.tow.gallons;
  const pts = props.calc.curve.filter((p) => p.gallons <= towGal + 1e-9);
  const gen = d3
    .line<{ cg: number; weight: number }>()
    .x((d) => x(d.cg))
    .y((d) => y(d.weight));
  return gen(pts) ?? '';
});

const informationalCurvePath = computed(() => {
  const x = xScale.value;
  const y = yScale.value;
  const towGal = props.calc.tow.gallons;
  const pts = props.calc.curve.filter((p) => p.gallons >= towGal - 1e-9);
  const gen = d3
    .line<{ cg: number; weight: number }>()
    .x((d) => x(d.cg))
    .y((d) => y(d.weight));
  return gen(pts) ?? '';
});

const xTicks = computed(() => {
  const scale = xScale.value;
  return scale
    .ticks(Math.max(2, Math.floor(innerWidth.value / 70)))
    .map((t) => ({ x: scale(t), label: t.toFixed(1) }));
});

const yTicks = computed(() => {
  const scale = yScale.value;
  return scale
    .ticks(6)
    .map((v) => ({ y: scale(v), label: Math.round(v).toLocaleString() }));
});

// A plain literal object (not Record<string, string>) so each property
// access below is typed as `string`, not `string | undefined`.
const markerColors = {
  FFW: '#94a3b8',
  TOW: '#3b82f6',
  LDW: '#4ade80',
  ZFW: '#f59e0b',
} as const;

const markerRenders = computed(() => {
  const c = props.calc;
  const x = xScale.value;
  const y = yScale.value;
  const out: { label: string; x: number; y: number; color: string }[] = [];
  if (c.showFFW) {
    out.push({
      label: 'FFW',
      x: x(c.ffw.cg),
      y: y(c.ffw.weight),
      color: markerColors.FFW,
    });
  }
  out.push({
    label: 'TOW',
    x: x(c.tow.cg),
    y: y(c.tow.weight),
    color: markerColors.TOW,
  });
  out.push({
    label: 'LDW',
    x: x(c.ldw.cg),
    y: y(c.ldw.weight),
    color: markerColors.LDW,
  });
  out.push({
    label: 'ZFW',
    x: x(c.zfw.cg),
    y: y(c.zfw.weight),
    color: markerColors.ZFW,
  });
  return out;
});

// MLW/MZFW are only interesting as separate lines when they're actually
// below MTOW -- if MTOW isn't set (0) there's nothing to compare against.
const referenceLines = computed(() => {
  const y = yScale.value;
  const mtow = props.layout.maxTakeoffWeight;
  const lines: { y: number; label: string }[] = [];
  if (
    props.layout.maxLandingWeight > 0 &&
    mtow > 0 &&
    props.layout.maxLandingWeight < mtow
  ) {
    lines.push({ y: y(props.layout.maxLandingWeight), label: 'MLW' });
  }
  if (
    props.layout.maxZeroFuelWeight > 0 &&
    mtow > 0 &&
    props.layout.maxZeroFuelWeight < mtow
  ) {
    lines.push({ y: y(props.layout.maxZeroFuelWeight), label: 'MZFW' });
  }
  return lines;
});

const svgRoot = ref<SVGSVGElement | null>(null);
function svgString(): string {
  return svgRoot.value?.outerHTML ?? '';
}
defineExpose({ svgString });
</script>

<template>
  <div ref="containerRef" class="cg-chart">
    <svg
      ref="svgRoot"
      xmlns="http://www.w3.org/2000/svg"
      :width="containerWidth"
      :height="height"
    >
      <g :transform="`translate(${margin.left},${margin.top})`">
        <!-- Grid + Y axis -->
        <g v-for="tick in yTicks" :key="tick.y">
          <line
            x1="0"
            :y1="tick.y"
            :x2="innerWidth"
            :y2="tick.y"
            stroke="#2a2a2a"
          />
          <text
            :x="-8"
            :y="tick.y"
            text-anchor="end"
            dominant-baseline="middle"
            fill="#888"
            font-size="11"
          >
            {{ tick.label }}
          </text>
        </g>
        <line x1="0" y1="0" x2="0" :y2="innerHeight" stroke="#555" />
        <text
          :x="-margin.left + 12"
          :y="-4"
          fill="#888"
          font-size="10"
          text-anchor="start"
        >
          lb
        </text>

        <!-- X axis -->
        <g :transform="`translate(0,${innerHeight})`">
          <line x1="0" y1="0" :x2="innerWidth" y2="0" stroke="#555" />
          <g v-for="tick in xTicks" :key="tick.x">
            <line :x1="tick.x" y1="0" :x2="tick.x" y2="4" stroke="#555" />
            <text
              :x="tick.x"
              y="16"
              text-anchor="middle"
              fill="#888"
              font-size="11"
            >
              {{ tick.label }}
            </text>
          </g>
          <text
            :x="innerWidth"
            y="30"
            fill="#888"
            font-size="10"
            text-anchor="end"
          >
            in
          </text>
        </g>

        <!-- Max weight reference lines -->
        <g v-for="line in referenceLines" :key="line.label">
          <line
            x1="0"
            :y1="line.y"
            :x2="innerWidth"
            :y2="line.y"
            stroke="#f59e0b"
            stroke-width="1"
            stroke-dasharray="5,4"
            opacity="0.7"
          />
          <text
            :x="innerWidth - 4"
            :y="line.y - 4"
            text-anchor="end"
            fill="#f59e0b"
            font-size="10"
          >
            {{ line.label }}
          </text>
        </g>

        <!-- CG envelope (bold outline -- the "black polygon" from the spec,
             rendered light against this app's dark theme for visibility) -->
        <path
          :d="envelopePath"
          fill="none"
          stroke-width="2.5"
          class="envelope"
        />

        <!-- Fuel-burn curve: solid for the portion actually flown
             (ZFW→TOW), dotted above TOW (informational only -- "what if
             the tanks were fuller"), never actually flown. -->
        <path
          :d="informationalCurvePath"
          fill="none"
          stroke="#888"
          stroke-width="2"
          stroke-linejoin="round"
          stroke-dasharray="2,3"
        />
        <path
          :d="flownCurvePath"
          fill="none"
          stroke="#e0e0e0"
          stroke-width="2"
          stroke-linejoin="round"
        />

        <!-- Markers -->
        <g v-for="m in markerRenders" :key="m.label">
          <circle
            :cx="m.x"
            :cy="m.y"
            r="5"
            :fill="m.color"
            stroke="#111"
            stroke-width="1.5"
          />
          <text
            :x="m.x + 8"
            :y="m.y - 8"
            :fill="m.color"
            font-size="11"
            font-weight="700"
          >
            {{ m.label }}
          </text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped lang="scss">
.cg-chart {
  width: 100%;
  background: #161616;
  border-radius: 6px;
}

.envelope {
  stroke: #eee;
}
</style>

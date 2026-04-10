<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import * as d3 from 'd3';

export interface DataPoint {
  time: Date;
  value: number | null;
}

export interface GraphSeries {
  name: string;
  color: string;
  strokeWidth?: number;
  strokeDasharray?: string;
  data: DataPoint[];
}

const props = withDefaults(
  defineProps<{
    series: GraphSeries[];
    height?: number;
    yMin?: number;
    yMax?: number;
  }>(),
  { height: 200, yMin: undefined, yMax: undefined }
);

const containerRef = ref<HTMLDivElement | null>(null);
const containerWidth = ref(300);

const margin = { top: 8, right: 12, bottom: 28, left: 42 };

const innerWidth = computed(() =>
  Math.max(0, containerWidth.value - margin.left - margin.right)
);
const innerHeight = computed(() => props.height - margin.top - margin.bottom);

onMounted(() => {
  if (!containerRef.value) {
    return;
  }
  containerWidth.value = containerRef.value.clientWidth;
  const ro = new ResizeObserver((entries) => {
    containerWidth.value = entries[0].contentRect.width;
  });
  ro.observe(containerRef.value);
  onUnmounted(() => ro.disconnect());
});

// All non-null points across all series.
const allPoints = computed(() =>
  props.series.flatMap((s) => s.data.filter((d) => d.value !== null))
);

const xScale = computed(() => {
  const times = allPoints.value.map((d) => d.time);
  const [t0, t1] = d3.extent(times) as [Date | undefined, Date | undefined];
  const now = new Date();
  return d3
    .scaleTime()
    .domain([t0 ?? now, t1 ?? now])
    .range([0, innerWidth.value]);
});

const yScale = computed(() => {
  const fixedMin = props.yMin;
  const fixedMax = props.yMax;

  if (fixedMin != null && fixedMax != null) {
    // Fixed range: clamp so out-of-range values peg to top/bottom edge.
    return d3
      .scaleLinear()
      .domain([fixedMin, fixedMax])
      .range([innerHeight.value, 0])
      .clamp(true);
  }

  const vals = allPoints.value.map((d) => d.value as number);
  const [mn, mx] = d3.extent(vals) as [number | undefined, number | undefined];
  const pad = mn != null && mx != null ? Math.max((mx - mn) * 0.1, 2) : 10;
  return d3
    .scaleLinear()
    .domain([mn != null ? mn - pad : 0, mx != null ? mx + pad : 100])
    .range([innerHeight.value, 0])
    .nice();
});

const lineGen = computed(() =>
  d3
    .line<DataPoint>()
    .defined((d) => d.value !== null)
    .x((d) => xScale.value(d.time))
    .y((d) => yScale.value(d.value as number))
    .curve(d3.curveMonotoneX)
);

const paths = computed(() =>
  // Reverse so first series in the array renders on top in SVG paint order.
  [...props.series].reverse().map((s) => ({
    name: s.name,
    color: s.color,
    strokeWidth: s.strokeWidth ?? 1.5,
    strokeDasharray: s.strokeDasharray ?? 'none',
    d: lineGen.value(s.data) ?? '',
  }))
);

function fmt12h(d: Date): string {
  const h = d.getHours() % 12 || 12;
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  const ampm = d.getHours() < 12 ? 'am' : 'pm';
  return `${h}:${m}:${s}${ampm}`;
}

const xTicks = computed(() => {
  const scale = xScale.value;
  const ticks = scale.ticks(Math.max(2, Math.floor(innerWidth.value / 80)));
  return ticks.map((t) => ({ x: scale(t), label: fmt12h(t) }));
});

const yTicks = computed(() => {
  const scale = yScale.value;
  const ticks = scale.ticks(5);
  return ticks.map((v) => ({ y: scale(v), label: String(Math.round(v)) }));
});

// ── Hover state ──────────────────────────────────────────────────────────────

const cursorX = ref<number | null>(null);
const cursorTime = ref<Date | null>(null);

interface HoverValue {
  name: string;
  color: string;
  strokeWidth: number;
  strokeDasharray: string;
  value: string;
}
const hoverValues = ref<HoverValue[]>([]);

function updateCursor(clientX: number) {
  const el = containerRef.value;
  if (!el) {
    return;
  }

  // Use the first series as the time axis reference — all series share the
  // same sample timestamps (they're built from the same history array).
  const ref = props.series[0];
  if (!ref?.data.length) {
    return;
  }

  const rect = el.getBoundingClientRect();
  const rawX = clientX - rect.left - margin.left;
  const clampedX = Math.max(0, Math.min(innerWidth.value, rawX));
  const t = xScale.value.invert(clampedX);

  // Find the index of the nearest data point by time.
  const bisect = d3.bisector<DataPoint, Date>((d) => d.time).center;
  const snapIdx = Math.min(
    Math.max(bisect(ref.data, t, 0), 0),
    ref.data.length - 1
  );
  const snapTime = ref.data[snapIdx].time;

  // Snap cursor to the actual sample's x position.
  cursorX.value = xScale.value(snapTime);
  cursorTime.value = snapTime;

  // Read values at the same index from every series (indices are aligned).
  hoverValues.value = props.series.map((s) => {
    const point = s.data[snapIdx];
    return {
      name: s.name,
      color: s.color,
      strokeWidth: s.strokeWidth ?? 1.5,
      strokeDasharray: s.strokeDasharray ?? 'none',
      value: point?.value != null ? point.value.toFixed(1) + '°F' : '—',
    };
  });
}

function onPointerMove(e: PointerEvent) {
  updateCursor(e.clientX);
}

function onPointerLeave() {
  cursorX.value = null;
  cursorTime.value = null;
  hoverValues.value = [];
}

// On touch devices pointerleave fires when you lift; suppress it briefly so
// the cursor stays visible after a tap.
let leaveTimer: ReturnType<typeof setTimeout> | null = null;

function onPointerDown(e: PointerEvent) {
  if (leaveTimer) {
    clearTimeout(leaveTimer);
    leaveTimer = null;
  }
  updateCursor(e.clientX);
}

function onPointerUp() {
  leaveTimer = setTimeout(() => {
    onPointerLeave();
    leaveTimer = null;
  }, 1500);
}

const cursorTimeLabel = computed(() =>
  cursorTime.value ? fmt12h(cursorTime.value) : ''
);

// Keep cursor updated when data changes (x scale may shift).
watch(
  () => props.series,
  () => {
    if (cursorX.value !== null && containerRef.value) {
      const rect = containerRef.value.getBoundingClientRect();
      updateCursor(rect.left + margin.left + cursorX.value);
    }
  },
  { deep: true }
);
</script>

<template>
  <div
    ref="containerRef"
    class="line-graph"
    @pointermove="onPointerMove"
    @pointerleave="onPointerLeave"
    @pointerdown="onPointerDown"
    @pointerup="onPointerUp"
  >
    <svg
      :width="containerWidth"
      :height="height"
      style="display: block; touch-action: none"
    >
      <g :transform="`translate(${margin.left},${margin.top})`">
        <!-- Grid + Y axis ticks -->
        <g>
          <line
            x1="0"
            :y1="0"
            x2="0"
            :y2="innerHeight"
            stroke="#444"
            stroke-width="1"
          />
          <g v-for="tick in yTicks" :key="tick.y">
            <line
              x1="0"
              :y1="tick.y"
              :x2="innerWidth"
              :y2="tick.y"
              stroke="#2a2a2a"
              stroke-width="1"
            />
            <text
              :x="-6"
              :y="tick.y"
              text-anchor="end"
              dominant-baseline="middle"
              fill="#888"
              font-size="11"
            >
              {{ tick.label }}
            </text>
          </g>
        </g>

        <!-- X axis -->
        <g :transform="`translate(0,${innerHeight})`">
          <line
            x1="0"
            y1="0"
            :x2="innerWidth"
            y2="0"
            stroke="#444"
            stroke-width="1"
          />
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
        </g>

        <!-- Data lines -->
        <path
          v-for="p in paths"
          :key="p.name"
          :d="p.d"
          fill="none"
          :stroke="p.color"
          :stroke-width="p.strokeWidth"
          :stroke-dasharray="p.strokeDasharray"
          stroke-linejoin="round"
          stroke-linecap="round"
        />

        <!-- Cursor -->
        <g v-if="cursorX !== null">
          <line
            :x1="cursorX"
            y1="0"
            :x2="cursorX"
            :y2="innerHeight"
            stroke="rgba(255,255,255,0.45)"
            stroke-width="1"
            stroke-dasharray="3,3"
          />
        </g>
      </g>
    </svg>

    <!-- Hover readout -->
    <div class="graph-hover" :class="{ visible: cursorX !== null }">
      <span class="gh-time">{{ cursorTimeLabel }}</span>
      <span v-for="v in hoverValues" :key="v.name" class="gh-item">
        <svg class="gh-swatch" width="24" height="12" aria-hidden="true">
          <line
            x1="0"
            y1="6"
            x2="24"
            y2="6"
            :stroke="v.color"
            :stroke-width="v.strokeWidth"
            :stroke-dasharray="v.strokeDasharray"
            stroke-linecap="round"
          />
        </svg>
        <span class="gh-name">{{ v.name }}</span>
        <span class="gh-val">{{ v.value }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.line-graph {
  width: 100%;
  user-select: none;
}

.graph-hover {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  min-height: 1.5rem;
  padding: 0.25rem 0;
  font-size: 0.8rem;
  color: #ccc;
  visibility: hidden;

  &.visible {
    visibility: visible;
  }
}

.gh-time {
  color: #aaa;
  font-variant-numeric: tabular-nums;
}

.gh-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.gh-swatch {
  flex-shrink: 0;
  overflow: visible;
}

.gh-name {
  color: #999;
}

.gh-val {
  font-weight: 600;
  color: #e0e0e0;
  font-variant-numeric: tabular-nums;
}
</style>

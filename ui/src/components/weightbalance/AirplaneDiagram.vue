<script setup lang="ts">
// Reusable top-down aircraft loading diagram: seats, cargo, and fuel
// stations positioned by each station's configured arm/lateral. Not to
// scale — one horizontal "slot" per distinct arm among the layout's
// seat/row/cargo stations, ordered nose (left) to tail (right). Purely
// presentational + an svgString() export for the save snapshot; all
// interaction (person picker, fuel slider) is left to the parent via the
// station-tap event, so this component has no fetch/router/websocket
// dependency and can be reused by a future panel calculator.
import { computed, ref } from 'vue';
import type { Layout, PositionValue, Lateral } from '@/types/weightbalance';
import { rowSeatKey } from '@/composables/useWeightBalanceCalc';

const props = defineProps<{
  layout: Layout;
  positions: Record<string, PositionValue>;
}>();

const emit = defineEmits<{
  'station-tap': [payload: { stationId: string; seatId?: string }];
}>();

// ── Geometry ─────────────────────────────────────────────────────────────
// The fuselage runs left-right (nose left, tail right), so a station's
// "arm" (fore-aft position) maps to X, and its "lateral" (left/center/
// right/full -- a position across the cabin) maps to Y, perpendicular to
// the fuselage centerline.
const ROW_SPACING = 130;
const NOSE_LEN = 130;
const TAIL_LEN = 90;
const FUSELAGE_HALF = 95;
const HEIGHT = 260;
const CY = HEIGHT / 2;
const LATERAL_OFFSET = 52; // Y offset for left/right seats & cargo
const SEAT_SPAN = 44; // shoulder-to-shoulder extent, across the cabin (Y)
const SEAT_DEPTH = 52; // front-to-back extent, along the fuselage (X)

// Fuel stations aren't drawn on the diagram itself -- the calculator shows
// them in its own fuel summary line, since that also needs taxi/trip/reserve
// figures the diagram doesn't know about.
const nonFuelStations = computed(() =>
  props.layout.stations.filter((s) => s.type !== 'fuel')
);

const uniqueArms = computed(() =>
  [...new Set(nonFuelStations.value.map((s) => s.arm))].sort((a, b) => a - b)
);
const rowCount = computed(() => Math.max(uniqueArms.value.length, 1));
const width = computed(
  () => NOSE_LEN + rowCount.value * ROW_SPACING + TAIL_LEN
);

function armX(arm: number): number {
  const idx = uniqueArms.value.indexOf(arm);
  return NOSE_LEN + (Math.max(idx, 0) + 0.5) * ROW_SPACING;
}

// left/right are positions across the cabin, which -- since the fuselage is
// drawn horizontally -- render as an offset above/below the centerline
// (top/bottom on screen), not left/right on screen: left is the bottom of
// the diagram, right is the top.
function lateralY(lateral?: Lateral): number {
  if (lateral === 'left') {
    return LATERAL_OFFSET;
  }
  if (lateral === 'right') {
    return -LATERAL_OFFSET;
  }
  return 0; // center, full
}

// Simplified fuselage outline: a long, straight (convex) "V" taper for the
// nose -- like a real top-down airplane nose, not a curve that pinches in
// early -- with just its very tip rounded off by a small arc, plus a
// rounded tail bulge at the right edge. Not to scale — just recognizable
// as a top-down airplane.
const fuselagePath = computed(() => {
  const w = width.value;
  const tailStart = w - TAIL_LEN;
  const half = FUSELAGE_HALF;
  const tipR = 18; // radius of the small rounding arc at the very nose tip
  return [
    `M ${NOSE_LEN} ${CY - half}`,
    `L ${tailStart} ${CY - half}`,
    `Q ${w - TAIL_LEN * 0.25} ${CY - half} ${w - 8} ${CY - half * 0.45}`,
    `Q ${w} ${CY} ${w - 8} ${CY + half * 0.45}`,
    `Q ${w - TAIL_LEN * 0.25} ${CY + half} ${tailStart} ${CY + half}`,
    `L ${NOSE_LEN} ${CY + half}`,
    `L ${tipR} ${CY + tipR}`,
    // Semicircular arc around the tip (through x=0), back up to the top
    // taper line's start -- sweep-flag=1 takes the west (left) side.
    `A ${tipR} ${tipR} 0 0 1 ${tipR} ${CY - tipR}`,
    'Z',
  ].join(' ');
});

// A pair of simple tapered wings crossing the fuselage, purely decorative.
// X offsets (chordwise width) are 3x a plain wing's; Y offsets (how far
// they reach out from the fuselage -- "height") are unchanged.
const wingsPath = computed(() => {
  const cx = NOSE_LEN + rowCount.value * ROW_SPACING * 0.42;
  const span = FUSELAGE_HALF + 60;
  const rootFwd = 24 * 3;
  const rootAft = 30 * 3;
  const tipFwd = 10 * 3;
  const tipAft = 40 * 3;
  return [
    `M ${cx - rootFwd} ${CY - FUSELAGE_HALF + 10}`,
    `L ${cx + tipFwd} ${CY - span}`,
    `L ${cx + tipAft} ${CY - span}`,
    `L ${cx + rootAft} ${CY - FUSELAGE_HALF + 10}`,
    'Z',
    `M ${cx - rootFwd} ${CY + FUSELAGE_HALF - 10}`,
    `L ${cx + tipFwd} ${CY + span}`,
    `L ${cx + tipAft} ${CY + span}`,
    `L ${cx + rootAft} ${CY + FUSELAGE_HALF - 10}`,
    'Z',
  ].join(' ');
});

// ── Seats (single-seat stations + row-station children) ────────────────────
interface SeatRender {
  key: string;
  stationId: string;
  seatId?: string;
  x: number;
  y: number;
  wide: boolean;
  name: string;
  weight: number;
  occupied: boolean;
}

const seatRenders = computed<SeatRender[]>(() => {
  const out: SeatRender[] = [];
  for (const station of nonFuelStations.value) {
    if (station.type === 'seat') {
      const pos = props.positions[station.id];
      out.push({
        key: station.id,
        stationId: station.id,
        x: armX(station.arm),
        y: CY + lateralY(station.lateral),
        wide: station.lateral === 'full',
        name: pos?.name || station.name,
        weight: pos?.weight ?? 0,
        occupied: !!pos && (!!pos.personId || (pos.weight ?? 0) > 0),
      });
    } else if (station.type === 'row') {
      // Missing/unrecognized item type is treated as a seat (data predating
      // the row-cargo option).
      for (const item of station.seats ?? []) {
        if (item.type === 'cargo') {
          continue; // rendered in cargoRenders below
        }
        const key = rowSeatKey(station.id, item.id);
        const pos = props.positions[key];
        out.push({
          key,
          stationId: station.id,
          seatId: item.id,
          x: armX(station.arm),
          y: CY + lateralY(item.lateral),
          wide: item.lateral === 'full',
          name: pos?.name || item.name,
          weight: pos?.weight ?? 0,
          occupied: !!pos && (!!pos.personId || (pos.weight ?? 0) > 0),
        });
      }
    }
  }
  return out;
});

// ── Cargo (top-level cargo stations + cargo items within a row) ────────────
interface CargoRender {
  key: string;
  stationId: string;
  seatId?: string;
  x: number;
  y: number;
  wide: boolean;
  name: string;
  weight: number;
}

const cargoRenders = computed<CargoRender[]>(() => {
  const out: CargoRender[] = [];
  for (const station of nonFuelStations.value) {
    if (station.type === 'cargo') {
      const pos = props.positions[station.id];
      out.push({
        key: station.id,
        stationId: station.id,
        x: armX(station.arm),
        y: CY + lateralY(station.lateral),
        wide: station.lateral === 'full',
        name: station.name,
        weight: pos?.weight ?? 0,
      });
    } else if (station.type === 'row') {
      for (const item of station.seats ?? []) {
        if (item.type !== 'cargo') {
          continue;
        }
        const key = rowSeatKey(station.id, item.id);
        const pos = props.positions[key];
        out.push({
          key,
          stationId: station.id,
          seatId: item.id,
          x: armX(station.arm),
          y: CY + lateralY(item.lateral),
          wide: item.lateral === 'full',
          name: item.name,
          weight: pos?.weight ?? 0,
        });
      }
    }
  }
  return out;
});

function tap(stationId: string, seatId?: string) {
  emit('station-tap', { stationId, seatId });
}

// ── Snapshot export ──────────────────────────────────────────────────────
const svgRoot = ref<SVGSVGElement | null>(null);
function svgString(): string {
  return svgRoot.value?.outerHTML ?? '';
}
defineExpose({ svgString });
</script>

<template>
  <div class="airplane-diagram">
    <svg
      ref="svgRoot"
      xmlns="http://www.w3.org/2000/svg"
      :viewBox="`0 0 ${width} ${HEIGHT}`"
      class="diagram-svg"
    >
      <path :d="wingsPath" class="wings" />
      <path :d="fuselagePath" class="fuselage" />

      <!-- Seats. The cushion is wider along X (fore-aft / depth) than Y
           (across the cabin / span) -- a "landscape" rectangle -- since the
           fuselage (and the direction a seat faces) runs along X here. -->
      <g
        v-for="seat in seatRenders"
        :key="seat.key"
        :transform="`translate(${seat.x},${seat.y})`"
        class="seat"
        :class="{ occupied: seat.occupied }"
        @click="tap(seat.stationId, seat.seatId)"
      >
        <rect
          class="seat-armrest"
          :x="-SEAT_DEPTH * 0.3"
          :y="(seat.wide ? -SEAT_SPAN * 1.6 : -SEAT_SPAN) / 2 - 5"
          :width="SEAT_DEPTH * 0.6"
          height="5"
          rx="2.5"
        />
        <rect
          class="seat-armrest"
          :x="-SEAT_DEPTH * 0.3"
          :y="(seat.wide ? SEAT_SPAN * 1.6 : SEAT_SPAN) / 2"
          :width="SEAT_DEPTH * 0.6"
          height="5"
          rx="2.5"
        />
        <rect
          class="seat-body"
          :x="-SEAT_DEPTH / 2"
          :y="(seat.wide ? -SEAT_SPAN * 1.6 : -SEAT_SPAN) / 2"
          :width="SEAT_DEPTH"
          :height="seat.wide ? SEAT_SPAN * 1.6 : SEAT_SPAN"
          rx="9"
        />
        <rect
          class="seat-back"
          :x="SEAT_DEPTH / 2 - 16"
          :y="(seat.wide ? -SEAT_SPAN * 1.6 : -SEAT_SPAN) * 0.32"
          width="12"
          :height="(seat.wide ? SEAT_SPAN * 1.6 : SEAT_SPAN) * 0.64"
          rx="5"
        />
        <template v-if="seat.occupied">
          <text class="seat-name" y="-4">{{ seat.name }}</text>
          <text class="seat-weight" y="14">{{ Math.round(seat.weight) }}</text>
        </template>
      </g>

      <!-- Cargo -->
      <g
        v-for="cargo in cargoRenders"
        :key="cargo.key"
        :transform="`translate(${cargo.x},${cargo.y})`"
        class="cargo"
        :class="{ empty: cargo.weight <= 0 }"
        @click="tap(cargo.stationId, cargo.seatId)"
      >
        <rect
          class="cargo-body"
          :x="-SEAT_DEPTH * 1.15 * 0.5"
          :y="(cargo.wide ? -SEAT_SPAN * 1.9 : -SEAT_SPAN) / 2"
          :width="SEAT_DEPTH * 1.15"
          :height="cargo.wide ? SEAT_SPAN * 1.9 : SEAT_SPAN"
          rx="8"
          :fill="cargo.weight > 0 ? 'url(#cargoHatch)' : undefined"
        />
        <rect
          class="cargo-chip"
          x="-22"
          y="-11"
          width="44"
          height="22"
          rx="4"
        />
        <text class="cargo-weight" y="6">{{ Math.round(cargo.weight) }}</text>
      </g>

      <defs>
        <pattern
          id="cargoHatch"
          patternUnits="userSpaceOnUse"
          width="8"
          height="8"
          patternTransform="rotate(45)"
        >
          <rect width="8" height="8" fill="#3a3a3a" />
          <line x1="0" y1="0" x2="0" y2="8" stroke="#6b6b6b" stroke-width="3" />
        </pattern>
      </defs>
    </svg>
  </div>
</template>

<style scoped lang="scss">
.airplane-diagram {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
}

.diagram-svg {
  width: 100%;
  max-width: 900px;
  height: auto;
}

.fuselage {
  fill: #1c1c1c;
  stroke: #444;
  stroke-width: 2;
}

.wings {
  fill: #181818;
  stroke: #383838;
  stroke-width: 1.5;
}

.seat {
  cursor: pointer;

  .seat-body {
    fill: #222;
    stroke: #444;
    stroke-width: 1.5;
    transition:
      fill 0.15s,
      stroke 0.15s;
  }

  .seat-back,
  .seat-armrest {
    fill: #2a2a2a;
    stroke: #444;
    stroke-width: 1;
  }

  .seat-name,
  .seat-weight {
    display: none;
  }

  &.occupied {
    .seat-body {
      fill: #1e3a5f;
      stroke: #3b82f6;
    }

    .seat-back,
    .seat-armrest {
      fill: #234a75;
      stroke: #3b82f6;
    }

    .seat-name,
    .seat-weight {
      display: block;
      text-anchor: middle;
      pointer-events: none;
    }

    .seat-name {
      fill: #fff;
      font-size: 10px;
      font-weight: 600;
    }

    .seat-weight {
      fill: #93c5fd;
      font-size: 13px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
  }

  &:hover .seat-body {
    stroke: #60a5fa;
  }
}

.cargo {
  cursor: pointer;

  .cargo-body {
    fill: #2a2a2a;
    stroke: #555;
    stroke-width: 1.5;
  }

  .cargo-chip {
    fill: #fff;
    opacity: 0.92;
  }

  .cargo-weight {
    text-anchor: middle;
    fill: #111;
    font-size: 13px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    pointer-events: none;
  }

  &.empty {
    .cargo-body {
      fill: #232323;
      stroke: #3a3a3a;
    }

    .cargo-chip {
      opacity: 0.5;
    }

    .cargo-weight {
      fill: #777;
    }
  }

  &:hover .cargo-body {
    stroke: #888;
  }
}
</style>

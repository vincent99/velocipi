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
const ROW_SPACING = 130;
const NOSE_LEN = 70;
const TAIL_LEN = 90;
const FUSELAGE_HALF = 95;
const HEIGHT = 260;
const CY = HEIGHT / 2;
const LATERAL_OFFSET = 52;
const SEAT_W = 44;
const SEAT_H = 52;

const nonFuelStations = computed(() =>
  props.layout.stations.filter((s) => s.type !== 'fuel')
);
const fuelStations = computed(() =>
  props.layout.stations.filter((s) => s.type === 'fuel')
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

function lateralOffset(lateral?: Lateral): number {
  if (lateral === 'left') {
    return -LATERAL_OFFSET;
  }
  if (lateral === 'right') {
    return LATERAL_OFFSET;
  }
  return 0; // center, full
}

// Simplified fuselage outline: pointed nose at x=0, rounded tail bulge at
// the right edge. Not to scale — just recognizable as a top-down airplane.
const fuselagePath = computed(() => {
  const w = width.value;
  const tailStart = w - TAIL_LEN;
  const half = FUSELAGE_HALF;
  return [
    `M ${NOSE_LEN} ${CY - half}`,
    `L ${tailStart} ${CY - half}`,
    `Q ${w - TAIL_LEN * 0.25} ${CY - half} ${w - 8} ${CY - half * 0.45}`,
    `Q ${w} ${CY} ${w - 8} ${CY + half * 0.45}`,
    `Q ${w - TAIL_LEN * 0.25} ${CY + half} ${tailStart} ${CY + half}`,
    `L ${NOSE_LEN} ${CY + half}`,
    `Q ${NOSE_LEN * 0.35} ${CY + half} 0 ${CY}`,
    `Q ${NOSE_LEN * 0.35} ${CY - half} ${NOSE_LEN} ${CY - half}`,
    'Z',
  ].join(' ');
});

// A pair of simple tapered wings crossing the fuselage, purely decorative.
const wingsPath = computed(() => {
  const cx = NOSE_LEN + rowCount.value * ROW_SPACING * 0.42;
  const span = FUSELAGE_HALF + 60;
  return [
    `M ${cx - 24} ${CY - FUSELAGE_HALF + 10}`,
    `L ${cx + 10} ${CY - span}`,
    `L ${cx + 40} ${CY - span}`,
    `L ${cx + 30} ${CY - FUSELAGE_HALF + 10}`,
    'Z',
    `M ${cx - 24} ${CY + FUSELAGE_HALF - 10}`,
    `L ${cx + 10} ${CY + span}`,
    `L ${cx + 40} ${CY + span}`,
    `L ${cx + 30} ${CY + FUSELAGE_HALF - 10}`,
    'Z',
  ].join(' ');
});

// ── Seats (single-seat stations + row-station children) ────────────────────
interface SeatRender {
  key: string;
  stationId: string;
  seatId?: string;
  x: number;
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
        x: armX(station.arm) + lateralOffset(station.lateral),
        wide: station.lateral === 'full',
        name: pos?.name || station.name,
        weight: pos?.weight ?? 0,
        occupied: !!pos && (!!pos.personId || (pos.weight ?? 0) > 0),
      });
    } else if (station.type === 'row') {
      for (const seat of station.seats ?? []) {
        const key = rowSeatKey(station.id, seat.id);
        const pos = props.positions[key];
        out.push({
          key,
          stationId: station.id,
          seatId: seat.id,
          x: armX(station.arm) + lateralOffset(seat.lateral),
          wide: seat.lateral === 'full',
          name: pos?.name || seat.name,
          weight: pos?.weight ?? 0,
          occupied: !!pos && (!!pos.personId || (pos.weight ?? 0) > 0),
        });
      }
    }
  }
  return out;
});

// ── Cargo ────────────────────────────────────────────────────────────────
interface CargoRender {
  key: string;
  stationId: string;
  x: number;
  wide: boolean;
  name: string;
  weight: number;
}

const cargoRenders = computed<CargoRender[]>(() =>
  nonFuelStations.value
    .filter((s) => s.type === 'cargo')
    .map((station) => {
      const pos = props.positions[station.id];
      return {
        key: station.id,
        stationId: station.id,
        x: armX(station.arm) + lateralOffset(station.lateral),
        wide: station.lateral === 'full',
        name: station.name,
        weight: pos?.weight ?? 0,
      };
    })
);

// ── Fuel readouts (shown centered below the diagram) ────────────────────────
const fuelRenders = computed(() =>
  fuelStations.value.map((station) => ({
    key: station.id,
    stationId: station.id,
    name: station.name,
    gallons: props.positions[station.id]?.gallons ?? 0,
    capacityGal: station.capacityGal ?? 0,
  }))
);

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

      <!-- Seats -->
      <g
        v-for="seat in seatRenders"
        :key="seat.key"
        :transform="`translate(${seat.x},${CY})`"
        class="seat"
        :class="{ occupied: seat.occupied }"
        @click="tap(seat.stationId, seat.seatId)"
      >
        <rect
          class="seat-armrest"
          :x="(seat.wide ? -SEAT_W * 1.6 : -SEAT_W) / 2 - 5"
          :y="-SEAT_H * 0.3"
          width="5"
          :height="SEAT_H * 0.6"
          rx="2.5"
        />
        <rect
          class="seat-armrest"
          :x="(seat.wide ? SEAT_W * 1.6 : SEAT_W) / 2"
          :y="-SEAT_H * 0.3"
          width="5"
          :height="SEAT_H * 0.6"
          rx="2.5"
        />
        <rect
          class="seat-body"
          :x="(seat.wide ? -SEAT_W * 1.6 : -SEAT_W) / 2"
          :y="-SEAT_H / 2"
          :width="seat.wide ? SEAT_W * 1.6 : SEAT_W"
          :height="SEAT_H"
          rx="9"
        />
        <rect
          class="seat-back"
          :x="(seat.wide ? -SEAT_W * 1.6 : -SEAT_W) * 0.32"
          :y="-SEAT_H / 2 + 4"
          :width="(seat.wide ? SEAT_W * 1.6 : SEAT_W) * 0.64"
          height="12"
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
        :transform="`translate(${cargo.x},${CY})`"
        class="cargo"
        :class="{ empty: cargo.weight <= 0 }"
        @click="tap(cargo.stationId)"
      >
        <rect
          class="cargo-body"
          :x="(cargo.wide ? SEAT_W * 1.9 : SEAT_W * 1.15) / -2"
          :y="-SEAT_H / 2"
          :width="cargo.wide ? SEAT_W * 1.9 : SEAT_W * 1.15"
          :height="SEAT_H"
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

    <!-- Fuel readouts, centered below the diagram -->
    <div v-if="fuelRenders.length" class="fuel-row">
      <button
        v-for="fuel in fuelRenders"
        :key="fuel.key"
        type="button"
        class="fuel-pill"
        @click="tap(fuel.stationId)"
      >
        <span class="fuel-name">{{ fuel.name }}</span>
        <span class="fuel-gal"
          >{{ fuel.gallons.toFixed(1) }} /
          {{ fuel.capacityGal.toFixed(0) }} gal</span
        >
      </button>
    </div>
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

.fuel-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.5rem;
}

.fuel-pill {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 8px;
  padding: 0.4rem 0.9rem;
  color: #e0e0e0;
  cursor: pointer;

  &:hover {
    border-color: #3b82f6;
  }
}

.fuel-name {
  font-size: 0.72rem;
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.fuel-gal {
  font-size: 0.95rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>

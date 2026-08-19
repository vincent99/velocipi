<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import type {
  Layout,
  Person,
  PositionValue,
  SavedWB,
} from '@/types/weightbalance';
import {
  useWeightBalanceCalc,
  rowSeatKey,
} from '@/composables/useWeightBalanceCalc';
import { combineSvgSnapshot } from '@/lib/svgSnapshot';
import AirplaneDiagram from '@/components/weightbalance/AirplaneDiagram.vue';
import CGChart from '@/components/weightbalance/CGChart.vue';
import ErrorList from '@/components/weightbalance/ErrorList.vue';
import SeatPickerPopover from '@/components/weightbalance/SeatPickerPopover.vue';
import CargoPopover from '@/components/weightbalance/CargoPopover.vue';
import FuelPopover from '@/components/weightbalance/FuelPopover.vue';

const layouts = ref<Layout[]>([]);
const people = ref<Person[]>([]);
const selectedLayoutId = ref<string | null>(null);
const positions = ref<Record<string, PositionValue>>({});
const taxiFuelGal = ref(0);
const tripFuelGal = ref(0);

const loading = ref(true);
const error = ref('');
const layoutMismatch = ref(false);
const saveFlash = ref(false);

const selectedLayout = ref<Layout | null>(null);

const diagramRef = ref<InstanceType<typeof AirplaneDiagram> | null>(null);
const chartRef = ref<InstanceType<typeof CGChart> | null>(null);

const calc = useWeightBalanceCalc(
  selectedLayout,
  positions,
  taxiFuelGal,
  tripFuelGal
);

onMounted(async () => {
  loading.value = true;
  try {
    const [layoutsRes, peopleRes, latestRes] = await Promise.all([
      fetch('/wb/layouts'),
      fetch('/wb/people'),
      fetch('/wb/saved/latest'),
    ]);
    layouts.value = layoutsRes.ok ? await layoutsRes.json() : [];
    people.value = peopleRes.ok ? await peopleRes.json() : [];

    if (latestRes.ok) {
      const saved: SavedWB = await latestRes.json();
      const layout = layouts.value.find((l) => l.id === saved.layoutId);
      if (layout) {
        selectedLayoutId.value = layout.id;
        selectedLayout.value = layout;
        positions.value = saved.positions ?? {};
        taxiFuelGal.value = saved.taxiFuelGal ?? 0;
        tripFuelGal.value = saved.tripFuelGal ?? 0;
        layoutMismatch.value =
          !!saved.layoutHash && saved.layoutHash !== layout.hash;
      }
    }

    const firstLayout = layouts.value[0];
    if (!selectedLayout.value && firstLayout) {
      selectedLayoutId.value = firstLayout.id;
      selectedLayout.value = firstLayout;
    }
  } catch (e: unknown) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
});

function onLayoutChange() {
  selectedLayout.value =
    layouts.value.find((l) => l.id === selectedLayoutId.value) ?? null;
  positions.value = {};
  layoutMismatch.value = false;
}

// ── Station tap → popover ───────────────────────────────────────────────────
type PopoverState =
  | { kind: 'seat'; stationId: string; seatId?: string; title: string }
  | { kind: 'cargo'; stationId: string; title: string }
  | { kind: 'fuel'; stationId: string; title: string; capacityGal: number }
  | null;
const popover = ref<PopoverState>(null);

function positionKey(p: PopoverState): string {
  if (!p) {
    return '';
  }
  if (p.kind === 'seat' && p.seatId) {
    return rowSeatKey(p.stationId, p.seatId);
  }
  return p.stationId;
}

function onStationTap({
  stationId,
  seatId,
}: {
  stationId: string;
  seatId?: string;
}) {
  const station = selectedLayout.value?.stations.find(
    (s) => s.id === stationId
  );
  if (!station) {
    return;
  }
  if (station.type === 'seat') {
    popover.value = { kind: 'seat', stationId, title: station.name || 'Seat' };
  } else if (station.type === 'row') {
    const seat = station.seats?.find((s) => s.id === seatId);
    popover.value = {
      kind: 'seat',
      stationId,
      seatId,
      title: seat?.name || station.name || 'Seat',
    };
  } else if (station.type === 'cargo') {
    popover.value = {
      kind: 'cargo',
      stationId,
      title: station.name || 'Cargo',
    };
  } else if (station.type === 'fuel') {
    popover.value = {
      kind: 'fuel',
      stationId,
      title: station.name || 'Fuel',
      capacityGal: station.capacityGal ?? 0,
    };
  }
}

const popoverCurrent = computed<PositionValue | undefined>(() =>
  popover.value ? positions.value[positionKey(popover.value)] : undefined
);

function setPosition(value: PositionValue) {
  const key = positionKey(popover.value);
  if (!key) {
    return;
  }
  positions.value = { ...positions.value, [key]: value };
}

function clearPosition() {
  const key = positionKey(popover.value);
  if (!key) {
    return;
  }
  const next = { ...positions.value };
  delete next[key];
  positions.value = next;
  popover.value = null;
}

function onSelectPerson(value: PositionValue) {
  setPosition(value);
  popover.value = null;
}
function onSetCargoWeight(weight: number) {
  setPosition({ weight });
  popover.value = null;
}
function onFuelUpdate(gallons: number) {
  setPosition({ gallons });
}

// ── Clear (keeps ignoreClear seats; always clears cargo/fuel) ───────────────
function clearAll() {
  const layout = selectedLayout.value;
  if (!layout) {
    return;
  }
  const kept: Record<string, PositionValue> = {};
  for (const station of layout.stations) {
    if (station.type === 'seat' && station.ignoreClear) {
      const existing = positions.value[station.id];
      if (existing) {
        kept[station.id] = existing;
      }
    } else if (station.type === 'row') {
      for (const seat of station.seats ?? []) {
        if (seat.ignoreClear) {
          const key = rowSeatKey(station.id, seat.id);
          const existing = positions.value[key];
          if (existing) {
            kept[key] = existing;
          }
        }
      }
    }
  }
  positions.value = kept;
  layoutMismatch.value = false;
}

// ── Save (manual button + autosave on leaving the page) ─────────────────────
async function saveSnapshot() {
  const layout = selectedLayout.value;
  if (!layout) {
    return;
  }
  const svg = combineSvgSnapshot(
    [diagramRef.value?.svgString() ?? '', chartRef.value?.svgString() ?? ''],
    layout.name
  );
  const data = {
    layoutId: layout.id,
    layoutName: layout.name,
    layoutHash: layout.hash ?? '',
    taxiFuelGal: taxiFuelGal.value,
    tripFuelGal: tripFuelGal.value,
    positions: positions.value,
  };
  try {
    await fetch('/wb/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, svg }),
    });
  } catch (e: unknown) {
    console.error('weight & balance: save failed', e);
  }
}

async function onSaveClick() {
  await saveSnapshot();
  saveFlash.value = true;
  setTimeout(() => {
    saveFlash.value = false;
  }, 2500);
}

onBeforeRouteLeave(async () => {
  if (selectedLayout.value) {
    await saveSnapshot();
  }
});

// ── Summary rows (FFW/TOW/LDW/ZFW) ──────────────────────────────────────────
const summaryRows = computed(() => {
  if (!calc.value) {
    return [];
  }
  const rows = [];
  if (calc.value.showFFW) {
    rows.push({ label: 'FFW', point: calc.value.ffw });
  }
  rows.push({ label: 'TOW', point: calc.value.tow });
  rows.push({ label: 'LDW', point: calc.value.ldw });
  rows.push({ label: 'ZFW', point: calc.value.zfw });
  return rows;
});
</script>

<template>
  <div class="wb-calculator">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="layouts.length === 0" class="hint">
      No layouts configured yet — define one on the Setup tab.
    </div>

    <template v-else>
      <div class="wb-toolbar">
        <label class="layout-select-label">
          Layout
          <select v-model="selectedLayoutId" @change="onLayoutChange">
            <option v-for="l in layouts" :key="l.id" :value="l.id">
              {{ l.name }}
            </option>
          </select>
        </label>

        <label class="fuel-input-label">
          Taxi fuel (gal)
          <input
            v-model.number="taxiFuelGal"
            type="number"
            min="0"
            step="0.1"
          />
        </label>
        <label class="fuel-input-label">
          Trip fuel (gal)
          <input
            v-model.number="tripFuelGal"
            type="number"
            min="0"
            step="0.1"
          />
        </label>

        <div class="toolbar-spacer" />

        <span v-if="saveFlash" class="save-flash">Saved ✓</span>
        <button type="button" class="clear-btn" @click="clearAll">Clear</button>
        <button type="button" class="save-btn" @click="onSaveClick">
          Save
        </button>
      </div>

      <p v-if="layoutMismatch" class="mismatch-banner">
        This layout's definition has changed since the loaded save was made —
        double-check stations, limits, and fuel before relying on this
        calculation.
      </p>

      <div v-if="selectedLayout && calc" class="wb-body">
        <AirplaneDiagram
          ref="diagramRef"
          :layout="selectedLayout"
          :positions="positions"
          @station-tap="onStationTap"
        />

        <div class="wb-summary">
          <div v-for="row in summaryRows" :key="row.label" class="summary-item">
            <span class="summary-label">{{ row.label }}</span>
            <span class="summary-val"
              >{{ Math.round(row.point.weight) }} lb @
              {{ row.point.cg.toFixed(1) }} in</span
            >
          </div>
        </div>

        <ErrorList :errors="calc.errors" />

        <CGChart ref="chartRef" :layout="selectedLayout" :calc="calc" />
      </div>
    </template>

    <SeatPickerPopover
      v-if="popover?.kind === 'seat'"
      :title="popover.title"
      :people="people"
      :current="popoverCurrent"
      @select="onSelectPerson"
      @clear="clearPosition"
      @cancel="popover = null"
    />
    <CargoPopover
      v-if="popover?.kind === 'cargo'"
      :title="popover.title"
      :weight="popoverCurrent?.weight ?? 0"
      @set="onSetCargoWeight"
      @clear="clearPosition"
      @cancel="popover = null"
    />
    <FuelPopover
      v-if="popover?.kind === 'fuel'"
      :title="popover.title"
      :capacity-gal="popover.capacityGal"
      :gallons="popoverCurrent?.gallons ?? 0"
      @update="onFuelUpdate"
      @close="popover = null"
    />
  </div>
</template>

<style scoped lang="scss">
.wb-calculator {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem 1.25rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  color: #e0e0e0;
}

.loading,
.hint {
  color: #888;
  padding: 2rem;
  text-align: center;
}

.error-banner {
  background: #5a1a1a;
  border: 1px solid #a33;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  color: #f88;
}

.wb-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1rem;
}

.layout-select-label,
.fuel-input-label {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.75rem;
  color: #999;

  select,
  input {
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 0.35rem 0.5rem;
    font-size: 0.85rem;
  }
}

.fuel-input-label input {
  width: 90px;
}

.toolbar-spacer {
  flex: 1;
}

.save-flash {
  color: #4ade80;
  font-size: 0.85rem;
  align-self: center;
}

.clear-btn {
  background: none;
  border: 1px solid #555;
  border-radius: 4px;
  color: #ccc;
  padding: 0.4rem 0.9rem;
  font-size: 0.85rem;
  cursor: pointer;

  &:hover {
    border-color: #888;
    color: #fff;
  }
}

.save-btn {
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  color: #fff;
  padding: 0.4rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    background: #2563eb;
  }
}

.mismatch-banner {
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.4);
  border-radius: 6px;
  padding: 0.5rem 0.85rem;
  color: #fbbf24;
  font-size: 0.82rem;
  margin: 0;
}

.wb-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.wb-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.5rem;
  justify-content: center;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.6rem 1rem;
}

.summary-item {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
}

.summary-label {
  font-size: 0.75rem;
  font-weight: 700;
  color: #888;
}

.summary-val {
  font-size: 0.88rem;
  font-weight: 600;
  color: #e0e0e0;
  font-variant-numeric: tabular-nums;
}
</style>

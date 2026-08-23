<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
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
import FuelSummary from '@/components/weightbalance/FuelSummary.vue';
import SeatPickerPopover from '@/components/weightbalance/SeatPickerPopover.vue';
import CargoPopover from '@/components/weightbalance/CargoPopover.vue';
import FuelPopover from '@/components/weightbalance/FuelPopover.vue';

const router = useRouter();

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

/** Matching key for carrying a position over between layouts: station name
 * alone for top-level stations, "row name:item name" for a row's children
 * (disambiguates e.g. two different rows each having a "Left" seat). */
function nameKey(stationName: string, itemName?: string): string {
  return itemName != null ? `${stationName}:${itemName}` : stationName;
}

function selectLayout(id: string) {
  const oldLayout = selectedLayout.value;
  const oldPositions = positions.value;
  const newLayout = layouts.value.find((l) => l.id === id) ?? null;

  selectedLayoutId.value = id;
  selectedLayout.value = newLayout;
  layoutMismatch.value = false;

  if (!oldLayout || !newLayout) {
    positions.value = {};
    return;
  }

  // Carry over fuel quantities and seat/cargo weights for any station (or
  // row item) that exists -- by name -- in both layouts; anything without a
  // same-named match in the new layout is left empty. Ids aren't useful for
  // this since they're freshly generated per layout, so matching is by name.
  const byName = new Map<string, PositionValue>();
  for (const station of oldLayout.stations) {
    if (station.type === 'row') {
      for (const item of station.seats ?? []) {
        const v = oldPositions[rowSeatKey(station.id, item.id)];
        if (v) {
          byName.set(nameKey(station.name, item.name), v);
        }
      }
    } else {
      const v = oldPositions[station.id];
      if (v) {
        byName.set(nameKey(station.name), v);
      }
    }
  }

  const next: Record<string, PositionValue> = {};
  for (const station of newLayout.stations) {
    if (station.type === 'row') {
      for (const item of station.seats ?? []) {
        const v = byName.get(nameKey(station.name, item.name));
        if (v) {
          next[rowSeatKey(station.id, item.id)] = v;
        }
      }
    } else {
      const v = byName.get(nameKey(station.name));
      if (v) {
        next[station.id] = v;
      }
    }
  }
  positions.value = next;
}

function goToSetup() {
  router.push('/remote/weightbalance/setup');
}

// ── Station tap → popover ───────────────────────────────────────────────────
type PopoverState =
  | {
      kind: 'seat';
      stationId: string;
      seatId?: string;
      title: string;
      maxWeight: number;
    }
  | {
      kind: 'cargo';
      stationId: string;
      seatId?: string;
      title: string;
      maxWeight: number;
    }
  | { kind: 'fuel'; stationId: string; title: string; capacityGal: number }
  | null;
const popover = ref<PopoverState>(null);

function positionKey(p: PopoverState): string {
  if (!p) {
    return '';
  }
  if ((p.kind === 'seat' || p.kind === 'cargo') && p.seatId) {
    return rowSeatKey(p.stationId, p.seatId);
  }
  return p.stationId;
}

// Weight slider max: the position's own limit, else the row's limit (for a
// row item), else a fallback default -- see StationEditor/LayoutEditor for
// where these limits are configured.
const DEFAULT_MAX_WEIGHT = 300;
function resolveMaxWeight(
  stationWeightLimit: number | undefined,
  itemWeightLimit?: number
): number {
  return itemWeightLimit ?? stationWeightLimit ?? DEFAULT_MAX_WEIGHT;
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
    popover.value = {
      kind: 'seat',
      stationId,
      title: station.name || 'Seat',
      maxWeight: resolveMaxWeight(station.weightLimit),
    };
  } else if (station.type === 'row') {
    // Missing/unrecognized item type is treated as a seat (data predating
    // the row-cargo option).
    const item = station.seats?.find((s) => s.id === seatId);
    const maxWeight = resolveMaxWeight(station.weightLimit, item?.weightLimit);
    if (item?.type === 'cargo') {
      popover.value = {
        kind: 'cargo',
        stationId,
        seatId,
        title: item.name || station.name || 'Cargo',
        maxWeight,
      };
    } else {
      popover.value = {
        kind: 'seat',
        stationId,
        seatId,
        title: item?.name || station.name || 'Seat',
        maxWeight,
      };
    }
  } else if (station.type === 'cargo') {
    popover.value = {
      kind: 'cargo',
      stationId,
      title: station.name || 'Cargo',
      maxWeight: resolveMaxWeight(station.weightLimit),
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

// ── People (saved via the seat popover -- there's no separate people editor) ─
async function savePeople() {
  try {
    await fetch('/wb/people', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(people.value),
    });
  } catch (e: unknown) {
    console.error('weight & balance: failed to save people', e);
  }
}

// A custom (non-picked) name+weight becomes a saved person: a new one if
// the name is new, or an overwrite of the existing person's weight if the
// name matches one already saved.
async function onSelectPerson(value: PositionValue) {
  if (!value.personId && value.name) {
    const existing = people.value.find((p) => p.name === value.name);
    if (existing) {
      existing.weight = value.weight ?? existing.weight;
      value.personId = existing.id;
    } else {
      const created: Person = {
        id: crypto.randomUUID(),
        name: value.name,
        weight: value.weight ?? 0,
      };
      people.value = [...people.value, created];
      value.personId = created.id;
    }
    await savePeople();
  }
  setPosition(value);
  popover.value = null;
}

async function onDeletePerson(id: string) {
  people.value = people.value.filter((p) => p.id !== id);
  await savePeople();
}

function onSetCargoWeight(weight: number) {
  setPosition({ weight });
  popover.value = null;
}
function onFuelUpdate(gallons: number) {
  setPosition({ gallons });
}

// ── Taxi / trip fuel popovers ────────────────────────────────────────────────
const taxiPopoverOpen = ref(false);
const tripPopoverOpen = ref(false);

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
    <div class="wb-toolbar">
      <div v-if="!loading && layouts.length" class="layout-box-list">
        <button
          v-for="l in layouts"
          :key="l.id"
          type="button"
          class="layout-box"
          :class="{ active: selectedLayoutId === l.id }"
          @click="selectLayout(l.id)"
        >
          {{ l.name || 'Unnamed' }}
        </button>
      </div>

      <div class="toolbar-spacer" />

      <span v-if="saveFlash" class="save-flash">Saved ✓</span>
      <template v-if="selectedLayout">
        <button type="button" class="clear-btn" @click="clearAll">Clear</button>
        <button type="button" class="save-btn" @click="onSaveClick">
          Save
        </button>
      </template>
      <button type="button" class="gear-btn" title="Setup" @click="goToSetup">
        <i class="fi-sr-settings-sliders" />
      </button>
    </div>

    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="layouts.length === 0" class="hint">
      No layouts configured yet — tap the gear icon to add one.
    </div>

    <template v-else>
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

        <FuelSummary
          :layout="selectedLayout"
          :positions="positions"
          :taxi-fuel-gal="taxiFuelGal"
          :trip-fuel-gal="tripFuelGal"
          @tap-fuel="(id) => onStationTap({ stationId: id })"
          @tap-taxi="taxiPopoverOpen = true"
          @tap-trip="tripPopoverOpen = true"
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
      :max-weight="popover.maxWeight"
      @select="onSelectPerson"
      @clear="clearPosition"
      @cancel="popover = null"
      @delete-person="onDeletePerson"
    />
    <CargoPopover
      v-if="popover?.kind === 'cargo'"
      :title="popover.title"
      :weight="popoverCurrent?.weight ?? 0"
      :max-weight="popover.maxWeight"
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
    <FuelPopover
      v-if="taxiPopoverOpen"
      title="Taxi fuel"
      :capacity-gal="calc?.loadedGal ?? 0"
      :gallons="taxiFuelGal"
      :show-shortcuts="false"
      @update="(v) => (taxiFuelGal = v)"
      @close="taxiPopoverOpen = false"
    />
    <FuelPopover
      v-if="tripPopoverOpen"
      title="Trip fuel"
      :capacity-gal="calc?.loadedGal ?? 0"
      :gallons="tripFuelGal"
      :show-shortcuts="false"
      @update="(v) => (tripFuelGal = v)"
      @close="tripPopoverOpen = false"
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

.layout-box-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.layout-box {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.4rem 0.9rem;
  color: #ccc;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;

  &:hover {
    border-color: #555;
  }

  &.active {
    background: #1e3a5f;
    border-color: #3b82f6;
    color: #90caf9;
  }
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

.gear-btn {
  background: none;
  border: 1px solid #555;
  border-radius: 4px;
  color: #ccc;
  padding: 0.4rem 0.6rem;
  font-size: 0.9rem;
  cursor: pointer;
  line-height: 1;

  &:hover {
    border-color: #888;
    color: #fff;
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

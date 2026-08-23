<script setup lang="ts">
import { computed } from 'vue';
import type { Layout, PositionValue } from '@/types/weightbalance';

const props = defineProps<{
  layout: Layout;
  positions: Record<string, PositionValue>;
  taxiFuelGal: number;
  tripFuelGal: number;
}>();

const emit = defineEmits<{
  'tap-fuel': [stationId: string];
  'tap-taxi': [];
  'tap-trip': [];
}>();

const fuelStations = computed(() =>
  props.layout.stations.filter((s) => s.type === 'fuel')
);

function gallonsAt(stationId: string): number {
  return props.positions[stationId]?.gallons ?? 0;
}

const totalLoadedGal = computed(() =>
  fuelStations.value.reduce((sum, s) => sum + gallonsAt(s.id), 0)
);

const reserveGal = computed(() => props.layout.reserveFuelGal);

// What's left after taxi, trip, and the reserve requirement are all
// subtracted from what's actually loaded. Deliberately not clamped at 0 --
// going negative here is exactly the "not enough fuel" condition the error
// list flags (see useWeightBalanceCalc's reserve check, which is the same
// inequality rearranged).
const extraGal = computed(
  () =>
    totalLoadedGal.value -
    props.taxiFuelGal -
    props.tripFuelGal -
    reserveGal.value
);
const extraError = computed(() => extraGal.value < -1e-9);
</script>

<template>
  <div class="fuel-line">
    <template v-for="(station, i) in fuelStations" :key="station.id">
      <span v-if="i > 0" class="fuel-op">+</span>
      <button
        type="button"
        class="fuel-chip"
        @click="emit('tap-fuel', station.id)"
      >
        <span class="fuel-chip-name">{{ station.name }}</span>
        <span class="fuel-chip-val"
          >{{ Math.round(gallonsAt(station.id)) }}/{{
            Math.round(station.capacityGal ?? 0)
          }}</span
        >
      </button>
    </template>

    <span v-if="fuelStations.length" class="fuel-op">−</span>
    <button type="button" class="fuel-chip" @click="emit('tap-taxi')">
      <span class="fuel-chip-name">Taxi</span>
      <span class="fuel-chip-val">{{ Math.round(taxiFuelGal) }}</span>
    </button>

    <span class="fuel-op">−</span>
    <button type="button" class="fuel-chip" @click="emit('tap-trip')">
      <span class="fuel-chip-name">Trip</span>
      <span class="fuel-chip-val">{{ Math.round(tripFuelGal) }}</span>
    </button>

    <span class="fuel-op">=</span>
    <div class="fuel-chip fuel-chip--plain">
      <span class="fuel-chip-name">Reserve</span>
      <span class="fuel-chip-val">{{ Math.round(reserveGal) }}</span>
    </div>
    <div class="fuel-chip fuel-chip--plain">
      <span class="fuel-chip-name">Extra</span>
      <span class="fuel-chip-val" :class="{ error: extraError }">{{
        Math.round(extraGal)
      }}</span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.fuel-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
}

.fuel-op {
  color: #666;
  font-size: 1rem;
  font-weight: 600;
}

.fuel-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 8px;
  padding: 0.35rem 0.75rem;
  color: #e0e0e0;
  cursor: pointer;

  &:hover {
    border-color: #3b82f6;
  }

  &--plain {
    background: none;
    border-color: transparent;
    cursor: default;
    padding: 0.35rem 0.4rem;

    &:hover {
      border-color: transparent;
    }
  }
}

.fuel-chip-name {
  font-size: 0.68rem;
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.fuel-chip-val {
  font-size: 0.9rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;

  &.error {
    color: #f87171;
  }
}
</style>

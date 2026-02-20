<script setup lang="ts">
import type { AirReading } from '../../types/ws';

defineProps<{
  reading: AirReading | null;
  lux: number | null;
}>();

function fmt(n: number | null | undefined, decimals: number): string {
  return n == null ? '--' : n.toFixed(decimals);
}
</script>

<template>
  <div class="air-reading" :class="{ stale: !reading }">
    <div class="reading-group">
      <span class="label">Temp</span>
      <span class="value">{{
        reading
          ? fmt(reading.tempF, 1) + '°F / ' + fmt(reading.tempC, 1) + '°C'
          : '--'
      }}</span>
    </div>
    <div class="reading-group">
      <span class="label">Humidity</span>
      <span class="value">{{
        reading ? fmt(reading.humidity, 1) + '%' : '--'
      }}</span>
    </div>
    <div class="reading-group">
      <span class="label">Pressure</span>
      <span class="value">{{
        reading ? fmt(reading.pressureInches, 2) + ' inHg' : '--'
      }}</span>
    </div>
    <div class="reading-group">
      <span class="label">Altitude</span>
      <span class="value">{{
        reading ? fmt(reading.pressureFeet, 0) + ' ft' : '--'
      }}</span>
    </div>
    <div class="reading-group">
      <span class="label">Dewpoint</span>
      <span class="value">{{
        reading ? fmt(reading.dewpointF, 1) + '°F' : '--'
      }}</span>
    </div>
    <div class="reading-group">
      <span class="label">Ambient Light</span>
      <span class="value">{{ lux != null ? fmt(lux, 1) + ' lux' : '--' }}</span>
    </div>
  </div>
</template>

<style scoped>
.air-reading {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
  margin: 0.75rem 0;
  font-size: 0.95rem;
}
.reading-group {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #888;
}
.value {
  font-size: 1.1rem;
  font-weight: 600;
  color: #eee;
  font-variant-numeric: tabular-nums;
}
.stale .value {
  color: #555;
}
</style>

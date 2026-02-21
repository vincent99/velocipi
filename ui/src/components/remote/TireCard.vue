<script setup lang="ts">
import type { Tire } from '@/types/ws';

defineProps<{
  position: string;
  tire: Tire | null;
}>();

function fmt(n: number | null | undefined, decimals: number): string {
  return n == null ? '--' : n.toFixed(decimals);
}
</script>

<template>
  <div class="tire-card" :class="{ stale: !tire }">
    <div class="tire-position">
      {{ position }}
    </div>
    <div
      class="tire-psi"
      :class="{
        flat: tire?.inflation === 'flat',
        warn: tire?.inflation === 'low' || tire?.inflation === 'decreasing',
      }"
    >
      {{ tire ? fmt(tire.pressurePsi, 1) + ' PSI' : '--' }}
    </div>
    <div class="tire-meta">
      {{
        tire
          ? fmt(tire.tempF, 0) + '°F · ' + fmt(tire.battery, 0) + '% batt'
          : '-- · --'
      }}
    </div>
    <div class="tire-state">
      {{ tire ? tire.inflation + ' · ' + tire.rotation : '--' }}
    </div>
  </div>
</template>

<style scoped lang="scss">
.tire-card {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;

  &.stale {
    opacity: 0.4;
  }
}
.tire-position {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #888;
  margin-bottom: 0.3rem;
}
.tire-psi {
  font-size: 1.4rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #eee;
  line-height: 1;

  &.warn { color: #f0a500; }
  &.flat { color: #e05555; }
}
.tire-meta {
  font-size: 0.75rem;
  color: #888;
  margin-top: 0.25rem;
  font-variant-numeric: tabular-nums;
}
.tire-state {
  font-size: 0.7rem;
  color: #666;
  margin-top: 0.15rem;
}
</style>

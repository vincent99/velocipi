<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    col: number;
    row: number;
    colSpan?: number;
    rowSpan?: number;
    value: number; // 0–100
    warnAt?: number; // default 80
    critAt?: number; // default 95
    label?: string;
  }>(),
  {
    colSpan: 1,
    rowSpan: 1,
    warnAt: 80,
    critAt: 95,
    label: undefined,
  }
);

const gridStyle = computed(() => ({
  gridColumn: `${props.col} / span ${props.colSpan}`,
  gridRow: `${props.row} / span ${props.rowSpan}`,
}));

const clampedValue = computed(() => Math.max(0, Math.min(100, props.value)));

const fillClass = computed(() => {
  if (clampedValue.value >= props.critAt) {
    return 'fill-crit';
  }
  if (clampedValue.value >= props.warnAt) {
    return 'fill-warn';
  }
  return 'fill-normal';
});
</script>

<template>
  <div :style="gridStyle" class="panel-progress-bar">
    <div class="bar-track">
      <div
        :class="['bar-fill', fillClass]"
        :style="{ width: `${clampedValue}%` }"
      />
    </div>
    <span v-if="label" class="bar-label">{{ label }}</span>
  </div>
</template>

<style scoped lang="scss">
.panel-progress-bar {
  display: flex;
  align-items: center;
  position: relative;
  overflow: hidden;
  box-sizing: border-box;
  border: 1px solid var(--panel-control-bg, #000000);
  background: var(--panel-control-bg, #000000);
  color: var(--panel-control-text, #ffffff);
  padding: 0 2px;
}

.bar-track {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.08);
}

.bar-fill {
  height: 100%;
  transition: width 0.3s ease;

  &.fill-normal {
    background: #3a8fd1;
  }
  &.fill-warn {
    background: #d18a3a;
  }
  &.fill-crit {
    background: #c0392b;
  }
}

.bar-label {
  position: relative;
  z-index: 1;
  font-size: 9px;
  opacity: 0.9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
  width: 100%;
}
</style>

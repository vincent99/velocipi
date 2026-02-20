<script setup lang="ts">
import type { LEDStateMsg } from '../../types/ws';

defineProps<{
  state: LEDStateMsg | null;
}>();

function ledLabel(state: LEDStateMsg | null): string {
  if (!state) {
    return 'LED: --';
  }
  if (state.mode === 'on') {
    return 'LED: on';
  }
  if (state.mode === 'blink') {
    return `LED: blink (${state.rate ?? 500}ms)`;
  }
  return 'LED: off';
}
</script>

<template>
  <div class="led-status">
    <div
      class="led-dot"
      :class="state?.mode"
      :style="
        state?.mode === 'blink'
          ? { '--blink-rate': (state.rate ?? 500) * 2 + 'ms' }
          : {}
      "
    />
    <span class="led-label">{{ ledLabel(state) }}</span>
  </div>
</template>

<style scoped>
.led-status {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin: 0.5rem 0;
  font-size: 0.9rem;
}
.led-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #333;
  border: 1px solid #555;
  flex-shrink: 0;
}
.led-dot.on {
  background: #f5c518;
  border-color: #f5c518;
}
.led-dot.blink {
  background: #f5c518;
  border-color: #f5c518;
  animation: led-blink var(--blink-rate, 500ms) step-start infinite;
}
@keyframes led-blink {
  50% {
    background: #333;
    border-color: #555;
  }
}
.led-label {
  color: #aaa;
}
</style>

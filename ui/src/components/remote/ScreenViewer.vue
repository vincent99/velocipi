<script setup lang="ts">
import { computed } from 'vue';
import { useConfig } from '@/composables/useConfig';
import { useScreenSocket } from '@/composables/useScreenSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import RedX from '@/components/RedX.vue';

const { config } = useConfig();
const { frameUrl, connected, dropped } = useScreenSocket();
const { ledState } = useDeviceState();

const w = computed(() => config.value?.panel.width ?? 256);
const h = computed(() => config.value?.panel.height ?? 64);
const disconnected = computed(() => dropped.value && !connected.value);

const borderStyle = computed(() => {
  if (!ledState.value || ledState.value.mode === 'off') return {};
  const rate = (ledState.value.rate ?? 500) * 2;
  return ledState.value.mode === 'blink' ? { '--blink-rate': rate + 'ms' } : {};
});
</script>

<template>
  <div
    class="screen-wrap"
    :class="ledState?.mode ?? 'off'"
    :style="{ ...borderStyle, width: w + 'px', height: h + 'px' }"
  >
    <img v-if="frameUrl" class="screenshot" :src="frameUrl" alt="screenshot" />
    <div v-else class="no-signal" />
    <RedX v-if="disconnected" :stroke-width="2" />
  </div>
</template>

<style scoped lang="scss">
.screen-wrap {
  display: inline-block;
  position: relative;
  border: 2px solid black;
  border-radius: 2px;

  &.on {
    border-color: #e53e3e;
  }

  &.blink {
    border-color: #e53e3e;
    animation: screen-blink var(--blink-rate, 1000ms) step-start infinite;
  }
}

@keyframes screen-blink {
  50% {
    border-color: transparent;
  }
}

.screenshot,
.no-signal {
  display: block;
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
}

.no-signal {
  background: #111;
}
</style>

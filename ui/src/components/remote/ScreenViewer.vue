<script setup lang="ts">
import { computed } from 'vue';
import { useConfig } from '@/composables/useConfig';
import { useScreenSocket } from '@/composables/useScreenSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import RedX from '@/components/RedX.vue';

const props = withDefaults(defineProps<{ showLed?: boolean }>(), {
  showLed: true,
});

const { config } = useConfig();
const { frameUrl, connected, dropped } = useScreenSocket();
const { ledState } = useDeviceState();

const w = computed(() => config.value?.panel.width ?? 256);
const h = computed(() => config.value?.panel.height ?? 64);
const disconnected = computed(() => dropped.value && !connected.value);

const ledMode = computed(() => ledState.value?.mode ?? 'off');

const blinkStyle = computed(() => {
  if (ledMode.value !== 'blink') {
    return {};
  }
  const rate = (ledState.value!.rate ?? 500) * 2;
  return { '--blink-rate': rate + 'ms' };
});
</script>

<template>
  <div class="screen-wrap" :style="{ width: w + 'px', height: h + 'px' }">
    <img v-if="frameUrl" class="screenshot" :src="frameUrl" alt="screenshot" />
    <div v-else class="no-signal" />
    <RedX v-if="disconnected" :stroke-width="2" />
    <div
      v-if="props.showLed && ledMode !== 'off'"
      class="led-dot"
      :class="ledMode"
      :style="blinkStyle"
    />
  </div>
</template>

<style scoped lang="scss">
.screen-wrap {
  display: inline-block;
  position: relative;
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

.led-dot {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  top: -5px;
  left: -5px;
  z-index: 1;

  // bright core
  background: radial-gradient(
    circle at 35% 35%,
    #ff9999,
    #e53e3e 50%,
    #a00 100%
  );
  // layered glow: tight inner halo + soft outer bloom
  box-shadow:
    0 0 3px 1px rgba(229, 62, 62, 0.9),
    0 0 8px 3px rgba(229, 62, 62, 0.6),
    0 0 18px 6px rgba(229, 62, 62, 0.25);

  &.blink {
    animation: led-blink var(--blink-rate, 1000ms) step-start infinite;
  }
}

@keyframes led-blink {
  50% {
    background: radial-gradient(
      circle at 35% 35%,
      #553333,
      #3a1010 50%,
      #200 100%
    );
    box-shadow:
      0 0 2px 1px rgba(100, 20, 20, 0.4),
      0 0 4px 2px rgba(100, 20, 20, 0.2);
  }
}
</style>

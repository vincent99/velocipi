<script setup lang="ts">
import { useConfig } from '../../composables/useConfig';

defineProps<{ frameUrl: string | null }>();

const { config } = useConfig();
</script>

<template>
  <div class="screen-wrap">
    <img
      v-if="frameUrl"
      class="screenshot"
      :src="frameUrl"
      :style="{
        width: (config?.panel.width ?? 256) + 'px',
        height: (config?.panel.height ?? 64) + 'px',
      }"
      alt="screenshot"
    />
    <div
      v-else
      class="no-signal"
      :style="{
        width: (config?.panel.width ?? 256) + 'px',
        height: (config?.panel.height ?? 64) + 'px',
      }"
    />
  </div>
</template>

<style scoped lang="scss">
.screen-wrap {
  margin: 0.75rem 0;
}
.screenshot {
  display: block;
  image-rendering: pixelated;
}
.no-signal {
  display: block;
  background: #111;
  border: 1px solid #333;
}
</style>

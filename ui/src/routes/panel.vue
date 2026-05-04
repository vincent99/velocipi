<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue';
import { RouterView } from 'vue-router';
import NavMenu from '@/components/panel/NavMenu.vue';
import { useConfig } from '@/composables/useConfig';

const { config } = useConfig();
const panelWidth = computed(() => config.value?.panel.width ?? 256);
const panelHeight = computed(() => config.value?.panel.height ?? 64);

const appEl = document.getElementById('app')!;

function updateZoom() {
  const zoom = Math.max(1, Math.floor(window.innerWidth / panelWidth.value));
  appEl.style.zoom = String(zoom);
}

onMounted(() => {
  updateZoom();
  window.addEventListener('resize', updateZoom);
});

onUnmounted(() => {
  window.removeEventListener('resize', updateZoom);
  appEl.style.zoom = '';
});
</script>

<template>
  <div
    class="panel-root"
    :class="{ antialiasing: config?.antialiasing }"
    :style="{
      width: panelWidth + 'px',
      height: panelHeight + 'px',
      '--panel-w': panelWidth + 'px',
      '--panel-h': panelHeight + 'px',
    }"
  >
    <RouterView />
    <NavMenu :hide-delay="config.value?.navMenu.hideDelay" />
  </div>
</template>

<style lang="scss">
// Global reset for the OLED panel page — must not be scoped
@font-face {
  font-family: 'panel';
  src: url('/fonts/Roboto-Regular.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
}

@font-face {
  font-family: 'panel-mono';
  src: url('/fonts/Roboto-Regular.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
}

html,
body {
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: #000;
}
.panel-root * {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
</style>

<style scoped lang="scss">
.panel-root {
  background: #111;
  color: white;
  overflow: hidden;
  font-family: sans-serif, monospace;
  font-size: 12px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;

  &:not(.antialiasing) {
    font-synthesis: none;
    text-rendering: geometricPrecision;
    -webkit-font-smoothing: none;
    -moz-osx-font-smoothing: grayscale;
    font-smooth: never;
    image-rendering: pixelated;
  }
}
</style>

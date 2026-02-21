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
    :style="{ width: panelWidth + 'px', height: panelHeight + 'px' }"
  >
    <RouterView />
    <NavMenu />
  </div>
</template>

<style lang="scss">
// Global reset for the OLED panel page — must not be scoped
@font-face {
  font-family: 'Terminus';
  src: url('/fonts/TerminusTTF-4.49.3.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
}
@font-face {
  font-family: 'Terminus';
  src: url('/fonts/TerminusTTF-Bold-4.49.3.ttf') format('truetype');
  font-weight: bold;
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
  -webkit-font-smoothing: none;
  -moz-osx-font-smoothing: grayscale;
  font-smooth: never;
  background: #111;
  color: white;
  overflow: hidden;
  font-family: 'Terminus', monospace;
  position: relative;
}
h1 {
  font-size: 16px;
}
</style>

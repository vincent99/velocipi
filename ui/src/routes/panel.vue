<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { RouterView } from 'vue-router';
import NavMenu from '../components/panel/NavMenu.vue';

const appEl = document.getElementById('app')!;

function updateZoom() {
  const zoom = Math.max(1, Math.floor(window.innerWidth / 256));
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
  <div class="panel-root">
    <RouterView />
    <NavMenu />
  </div>
</template>

<style>
/* Global reset for the OLED panel page — must not be scoped */
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

<style scoped>
.panel-root {
  -webkit-font-smoothing: none;
  background: #111;
  color: white;
  overflow: hidden;
  width: 256px;
  height: 64px;
  font-family: sans-serif;
  position: relative;
}
h1 {
  font-size: 16px;
}
</style>

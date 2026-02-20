<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import KnobCounters from '../components/app/KnobCounters.vue'
import KeyDisplay from '../components/app/KeyDisplay.vue'

const appEl = document.getElementById('app')!

function updateZoom() {
  const zoom = Math.max(1, Math.floor(window.innerWidth / 256))
  appEl.style.zoom = String(zoom)
}

onMounted(() => {
  updateZoom()
  window.addEventListener('resize', updateZoom)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateZoom)
  appEl.style.zoom = ''
})
</script>

<template>
  <div class="app-root">
    <h1>Velocipi</h1>
    <KnobCounters />
    <KeyDisplay />
  </div>
</template>

<style>
/* Global reset for the OLED app page — must not be scoped */
html, body {
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: #000;
}
.app-root * {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
</style>

<style scoped>
.app-root {
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

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';

defineProps<{ frameUrl: string | null }>();

// frame.png is 2409x704. The transparent window is:
// x: 621–1803 (width 1182), y: 167–480 (height 313).
const SCREENSHOT_W = 256;
const FRAME_W = 2409;
const WINDOW_W = 1182;
const FRAME_MIN_W = Math.round((SCREENSHOT_W * FRAME_W) / WINDOW_W);

const frameWidth = ref(0);

function resize() {
  const available = document.documentElement.clientWidth - 32;
  const scale = Math.max(1, Math.floor(available / FRAME_MIN_W));
  frameWidth.value = scale * FRAME_MIN_W;
}

onMounted(() => {
  resize();
  window.addEventListener('resize', resize);
});
onUnmounted(() => window.removeEventListener('resize', resize));
</script>

<template>
  <div class="frame-wrap" :style="{ width: frameWidth + 'px' }">
    <img class="frame-img" src="/img/frame.png" alt="frame" />
    <div class="screen-window">
      <img
        v-if="frameUrl"
        class="screenshot"
        :src="frameUrl"
        alt="screenshot"
      />
    </div>
  </div>
</template>

<style scoped>
.frame-wrap {
  position: relative;
  display: inline-block;
}
.frame-img {
  display: block;
  width: 100%;
  height: auto;
}
/* Window hole percentages derived from frame dimensions:
   left=621/2409  right=606/2409  top=167/704  bottom=224/704 */
.screen-window {
  position: absolute;
  left: 25.78%;
  right: 25.11%;
  top: 23.72%;
  bottom: 31.82%;
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.screenshot {
  width: 100%;
  height: 100%;
  object-fit: fill;
  display: block;
  image-rendering: pixelated;
}
</style>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue';

const props = withDefaults(defineProps<{ text: string; speed?: number }>(), {
  speed: 30,
});

const containerRef = ref<HTMLElement | null>(null);
const textRef = ref<HTMLElement | null>(null);

// Applied to the inner <span>
const animStyle = ref<Record<string, string>>({});

let styleEl: HTMLStyleElement | null = null;
let uid = 0;

function updateAnimation() {
  const container = containerRef.value;
  const text = textRef.value;
  if (!container || !text) {
    return;
  }

  const cw = container.offsetWidth;
  const tw = text.scrollWidth;
  const overflow = tw - cw;

  // Remove previous injected style
  if (styleEl) {
    styleEl.remove();
    styleEl = null;
  }

  if (overflow <= 0) {
    animStyle.value = {};
    return;
  }

  // Unique name forces animation restart when text changes
  const name = `st-bounce-${uid++}`;
  const travelMs = (overflow / props.speed) * 1000;
  const pauseMs = 1000;
  const total = pauseMs + travelMs + pauseMs + travelMs;

  const p1 = ((pauseMs / total) * 100).toFixed(3);
  const p2 = (((pauseMs + travelMs) / total) * 100).toFixed(3);
  const p3 = (((pauseMs + travelMs + pauseMs) / total) * 100).toFixed(3);

  // 0%→p1%: pause at start; p1%→p2%: slide left; p2%→p3%: pause at end; p3%→100%: slide right back
  const cssBounce = `@keyframes ${name} {
    0%, ${p1}% { transform: translateX(0); }
    ${p2}%, ${p3}% { transform: translateX(-${overflow}px); }
    100% { transform: translateX(0); }
  }`;

  styleEl = document.createElement('style');
  styleEl.textContent = cssBounce;
  document.head.appendChild(styleEl);

  animStyle.value = {
    animation: `${name} ${(total / 1000).toFixed(3)}s linear infinite`,
    display: 'inline-block',
    willChange: 'transform',
  };
}

onMounted(() => {
  updateAnimation();
});

watch(
  () => props.text,
  async () => {
    // Wait for DOM to update with new text width
    await nextTick();
    updateAnimation();
  }
);

onUnmounted(() => {
  if (styleEl) {
    styleEl.remove();
  }
});
</script>

<template>
  <div ref="containerRef" class="scrolling-text">
    <span ref="textRef" :style="animStyle">{{ text }}</span>
  </div>
</template>

<style scoped>
.scrolling-text {
  overflow: hidden;
  white-space: nowrap;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
}
</style>

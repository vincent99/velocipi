<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';

const outer = ref(0);
const inner = ref(0);
const joy = ref(0);

const KNOB_MAP: Record<string, { counter: typeof outer; dir: number }> = {
  '[': { counter: outer, dir: -1 },
  ']': { counter: outer, dir: +1 },
  ';': { counter: inner, dir: -1 },
  "'": { counter: inner, dir: +1 },
  ',': { counter: joy, dir: -1 },
  '.': { counter: joy, dir: +1 },
};

function onKeyDown(e: KeyboardEvent) {
  const k = KNOB_MAP[e.key];
  if (k) {
    k.counter.value += k.dir;
  }
}

onMounted(() => document.addEventListener('keydown', onKeyDown));
onUnmounted(() => document.removeEventListener('keydown', onKeyDown));
</script>

<template>
  <div class="knobs">
    <span
      >out:<b>{{ outer }}</b></span
    >
    <span
      >in:<b>{{ inner }}</b></span
    >
    <span
      >joy:<b>{{ joy }}</b></span
    >
  </div>
</template>

<style scoped>
.knobs {
  position: absolute;
  top: 18px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  gap: 8px;
  font-size: 9px;
  color: #888;
  font-variant-numeric: tabular-nums;
}
b {
  color: #ccc;
}
</style>

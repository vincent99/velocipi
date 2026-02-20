<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';

const KEY_LABELS: Record<string, string> = {
  ArrowLeft: '◀',
  ArrowRight: '▶',
  ArrowUp: '▲',
  ArrowDown: '▼',
  Enter: '●',
  '[': '[',
  ']': ']',
  ';': '(',
  "'": ')',
  ',': '<',
  '.': '>',
};

const MOMENTARY = new Set(['[', ']', ';', "'", ',', '.']);
const timers: Record<string, ReturnType<typeof setTimeout>> = {};
const keyState = ref<Record<string, boolean>>({});

function onKeyDown(e: KeyboardEvent) {
  if (!(e.key in KEY_LABELS)) {
    return;
  }
  keyState.value = { ...keyState.value, [e.key]: true };
  if (MOMENTARY.has(e.key)) {
    clearTimeout(timers[e.key]);
    timers[e.key] = setTimeout(() => {
      keyState.value = { ...keyState.value, [e.key]: false };
    }, 150);
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (e.key in KEY_LABELS && !MOMENTARY.has(e.key)) {
    keyState.value = { ...keyState.value, [e.key]: false };
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown);
  document.addEventListener('keyup', onKeyUp);
});
onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown);
  document.removeEventListener('keyup', onKeyUp);
});
</script>

<template>
  <div class="keys">
    <span
      v-for="(label, key) in KEY_LABELS"
      :key="key"
      class="key"
      :class="{ active: keyState[key] }"
      >{{ label }}</span
    >
  </div>
</template>

<style scoped>
.keys {
  position: absolute;
  bottom: 2px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  gap: 3px;
}
.key {
  font-size: 9px;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #444;
  border-radius: 3px;
  color: #666;
  background: #1a1a1a;
}
.key.active {
  color: #fff;
  background: #333;
  border-color: #aaa;
}
</style>

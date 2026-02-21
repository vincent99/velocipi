<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const panelMeta: PanelMeta = {
  name: 'Kbd',
  icon: 'keyboard',
  sort: 99,
};
</script>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useConfig } from '@/composables/useConfig';

const { config } = useConfig();

const outer = ref(0);
const inner = ref(0);
const joy = ref(0);

const keyState = ref<Record<string, boolean>>({});
const timers: Record<string, ReturnType<typeof setTimeout>> = {};

const km = computed(() => config.value?.keyMap);

const encoderKeys = computed(() =>
  km.value
    ? new Set([
        km.value.outerLeft,
        km.value.outerRight,
        km.value.innerLeft,
        km.value.innerRight,
        km.value.joyLeft,
        km.value.joyRight,
      ])
    : new Set<string>()
);

function onKeyDown(e: KeyboardEvent) {
  const k = km.value;
  if (!k) {
    return;
  }

  keyState.value = { ...keyState.value, [e.key]: true };

  if (encoderKeys.value.has(e.key)) {
    clearTimeout(timers[e.key]);
    timers[e.key] = setTimeout(() => {
      keyState.value = { ...keyState.value, [e.key]: false };
    }, 150);

    if (e.key === k.outerLeft) outer.value--;
    else if (e.key === k.outerRight) outer.value++;
    else if (e.key === k.innerLeft) inner.value--;
    else if (e.key === k.innerRight) inner.value++;
    else if (e.key === k.joyLeft) joy.value--;
    else if (e.key === k.joyRight) joy.value++;
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (!encoderKeys.value.has(e.key)) {
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
  for (const t of Object.values(timers)) {
    clearTimeout(t);
  }
});
</script>

<template>
  <div class="kbd-root">
    <!-- Top half: 3 encoder columns -->
    <div v-if="km" class="encoders">
      <div class="enc-col">
        <span class="enc-label">Joy</span>
        <div class="enc-row">
          <div class="enc-btn" :class="{ active: keyState[km.joyLeft] }">◀</div>
          <span class="enc-value">{{ joy }}</span>
          <div class="enc-btn" :class="{ active: keyState[km.joyRight] }">
            ▶
          </div>
        </div>
      </div>
      <div class="enc-col">
        <span class="enc-label">Inner</span>
        <div class="enc-row">
          <div class="enc-btn" :class="{ active: keyState[km.innerLeft] }">
            ◀
          </div>
          <span class="enc-value">{{ inner }}</span>
          <div class="enc-btn" :class="{ active: keyState[km.innerRight] }">
            ▶
          </div>
        </div>
      </div>
      <div class="enc-col">
        <span class="enc-label">Outer</span>
        <div class="enc-row">
          <div class="enc-btn" :class="{ active: keyState[km.outerLeft] }">
            ◀
          </div>
          <span class="enc-value">{{ outer }}</span>
          <div class="enc-btn" :class="{ active: keyState[km.outerRight] }">
            ▶
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom half: 5 joystick buttons -->
    <div v-if="km" class="joy-row">
      <div class="key" :class="{ active: keyState[km.left] }">◀</div>
      <div class="key" :class="{ active: keyState[km.down] }">▼</div>
      <div class="key" :class="{ active: keyState[km.up] }">▲</div>
      <div class="key" :class="{ active: keyState[km.right] }">▶</div>
      <div class="key" :class="{ active: keyState[km.enter] }">●</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.kbd-root {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
}

// Top half: 3 encoder columns side by side
.encoders {
  height: 32px;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  padding: 1px 2px;
  gap: 2px;
}

.enc-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
}

.enc-row {
  display: flex;
  align-items: center;
  gap: 2px;
}

.enc-btn {
  width: 16px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #444;
  border: 1px solid #2a2a2a;
  border-radius: 2px;
  background: #0e0e0e;
  flex-shrink: 0;
  transition: background 0.05s, color 0.05s;

  &.active {
    background: #444;
    color: #fff;
    border-color: #888;
  }
}

.enc-label {
  font-size: 12px;
  color: #444;
}

.enc-value {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: #ccc;
  display: inline-block;
  min-width: 20px;
  text-align: center;
}

// Bottom half: 5 joy buttons
.joy-row {
  height: 32px;
  display: flex;
  align-items: stretch;
  padding: 2px 2px;
  gap: 2px;
}

.key {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #555;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  background: #0e0e0e;
  transition: background 0.05s, color 0.05s;

  &.active {
    background: #444;
    color: #fff;
    border-color: #aaa;
  }
}
</style>

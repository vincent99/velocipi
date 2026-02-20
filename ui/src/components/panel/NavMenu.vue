<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfig } from '../../composables/useConfig';
import { usePanelRoutes } from '../../composables/usePanelRoutes';

const panels = usePanelRoutes();
const route = useRoute();
const router = useRouter();
const { config } = useConfig();

const visible = ref(false);
const selectedIndex = ref(0);
const containerRef = ref<HTMLElement | null>(null);
let hideTimer: ReturnType<typeof setTimeout> | null = null;

const hideDelay = computed(() => config.value?.navMenu.hideDelay ?? 2000);
const cellWidth = computed(() => config.value?.navMenu.cellWidth ?? 60);
const containerWidth = computed(() => containerRef.value?.offsetWidth ?? 256);

const offset = computed(() => {
  const center =
    selectedIndex.value * cellWidth.value -
    (containerWidth.value / 2 - cellWidth.value / 2);
  const max = panels.length * cellWidth.value - containerWidth.value;
  return Math.max(0, Math.min(center, max));
});

function resetTimer() {
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
  }
  hideTimer = setTimeout(() => {
    visible.value = false;
    hideTimer = null;
  }, hideDelay.value);
}

const OUTER_KEYS: Record<string, 'left' | 'right'> = {
  '[': 'left',
  ']': 'right',
};

function onKeyDown(e: KeyboardEvent) {
  const dir = OUTER_KEYS[e.key];
  if (!dir) {
    return;
  }

  e.preventDefault();

  if (!visible.value) {
    const currentIndex = panels.findIndex((p) => p.path === route.path);
    selectedIndex.value = currentIndex >= 0 ? currentIndex : 0;
    visible.value = true;
    resetTimer();
    return;
  }

  if (dir === 'right') {
    selectedIndex.value = Math.min(selectedIndex.value + 1, panels.length - 1);
  } else {
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0);
  }

  router.push(panels[selectedIndex.value].path);
  resetTimer();
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown);
});

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown);
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
  }
});
</script>

<template>
  <div ref="containerRef" class="nav-anchor">
    <div v-if="visible" class="nav-overlay">
      <div class="nav-dim" />
      <div class="nav-bar">
        <div
          class="nav-strip"
          :style="{
            transform: `translateX(-${offset}px)`,
            width: `${panels.length * cellWidth}px`,
          }"
        >
          <div
            v-for="(p, i) in panels"
            :key="p.path"
            :class="['nav-cell', { selected: i === selectedIndex }]"
            :style="{ width: `${cellWidth}px` }"
          >
            <span class="nav-icon">{{ p.icon }}</span>
            <span class="nav-name">{{ p.name }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nav-anchor {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.nav-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
}

.nav-dim {
  position: absolute;
  inset: 0 0 32px 0;
  background: rgba(0, 0, 0, 0.5);
}

.nav-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 32px;
  overflow: hidden;
  background: #000;
  border-top: 1px solid #333;
}

.nav-strip {
  display: flex;
  height: 100%;
  transition: transform 0.15s ease;
}

.nav-cell {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  color: #fff;
}

.nav-cell.selected {
  background: #fff;
  color: #000;
}

.nav-icon {
  font-size: 12px;
  line-height: 1;
}

.nav-name {
  font-size: 8px;
  line-height: 1;
}
</style>

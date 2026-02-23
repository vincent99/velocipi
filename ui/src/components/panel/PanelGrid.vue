<script setup lang="ts">
import { provide, ref, computed } from 'vue';
import { usePanelGrid, PANEL_GRID_KEY } from '@/composables/usePanelGrid';
import { useConfig } from '@/composables/useConfig';
import type { PanelGridContext } from '@/composables/usePanelGrid';

// Per-control callbacks registered by index.
const innerCallbacks = ref<Map<number, (dir: 'left' | 'right') => void>>(
  new Map()
);
const confirmCallbacks = ref<Map<number, () => void>>(new Map());
const cancelCallbacks = ref<Map<number, () => void>>(new Map());

const grid = usePanelGrid({
  onInner(index, dir) {
    innerCallbacks.value.get(index)?.(dir);
  },
  onConfirm(index) {
    confirmCallbacks.value.get(index)?.();
  },
  onCancel(index) {
    cancelCallbacks.value.get(index)?.();
  },
});

const context: PanelGridContext = {
  registerControl(col: number, row: number) {
    return grid.registerControl(col, row);
  },
  selectedIndex: grid.selectedIndex,
  activeIndex: grid.activeIndex,
  registerCallbacks(
    index: number,
    onInner: (dir: 'left' | 'right') => void,
    onConfirm: () => void,
    onCancel: () => void
  ) {
    innerCallbacks.value.set(index, onInner);
    confirmCallbacks.value.set(index, onConfirm);
    cancelCallbacks.value.set(index, onCancel);
  },
};

provide(PANEL_GRID_KEY, context);

const { config } = useConfig();

const cssVars = computed(() => ({
  '--panel-bg': config.value?.panel.background ?? '#000000',
  '--panel-control-bg': config.value?.panel.controlBg ?? '#222222',
  '--panel-control-border': config.value?.panel.controlBorder ?? '#666666',
  '--panel-text': config.value?.panel.controlText ?? '#ffffff',
}));
</script>

<template>
  <div class="panel-grid" :style="cssVars">
    <slot />
  </div>
</template>

<style scoped lang="scss">
.panel-grid {
  position: absolute;
  inset: 0;
  display: grid;
  // 16 columns × 4 rows filling the 256×64px panel
  grid-template-columns: repeat(16, 1fr);
  grid-template-rows: repeat(4, 1fr);
  gap: 1px;
  background: var(--panel-bg, #000000);
}
</style>

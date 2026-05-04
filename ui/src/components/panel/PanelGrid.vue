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
  registerControl(col: number, row: number, colSpan: number, rowSpan: number) {
    return grid.registerControl(col, row, colSpan, rowSpan);
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

const cssVars = computed(() => {
  const p = config.value?.panel;
  return {
    '--panel-control-bg': p?.controlBackground ?? '#000000',
    '--panel-control-border': p?.controlBorder ?? '#444444',
    '--panel-control-text': p?.controlText ?? '#ffffff',
    '--panel-selected-bg': p?.selectedBackground ?? '#444444',
    '--panel-selected-border': p?.selectedBorder ?? '#888888',
    '--panel-selected-text': p?.selectedText ?? '#ffffff',
    '--panel-active-bg': p?.activeBackground ?? '#ffffff',
    '--panel-active-border': p?.activeBorder ?? '#888888',
    '--panel-active-text': p?.activeText ?? '#000000',
  };
});
</script>

<template>
  <div class="panel-grid" :style="cssVars">
    <slot />
  </div>
</template>

<style scoped lang="scss">
.panel-grid {
  display: grid;
  // 12 columns × 4 rows: 20×15px cells, 1px gap → 251×63px
  grid-template-columns: repeat(12, 20px);
  grid-template-rows: repeat(4, 15px);
  gap: 1px;
  flex-shrink: 0;
  background: var(--panel-control-bg, #000000);
}
</style>

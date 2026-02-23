<script setup lang="ts">
import { inject, computed, onMounted } from 'vue';
import { PANEL_GRID_KEY } from '@/composables/usePanelGrid';
import type { PanelGridContext } from '@/composables/usePanelGrid';

const emit = defineEmits<{
  inner: [dir: 'left' | 'right'];
  confirm: [];
  cancel: [];
}>();

// col/row: 1-based grid position; colSpan/rowSpan: how many cells to occupy
const props = withDefaults(
  defineProps<{
    col: number;
    row: number;
    colSpan?: number;
    rowSpan?: number;
  }>(),
  { colSpan: 1, rowSpan: 1 }
);

const grid = inject<PanelGridContext>(PANEL_GRID_KEY);
if (!grid) {
  throw new Error('PanelControl must be used inside PanelGrid');
}

const index = grid.registerControl(
  props.col,
  props.row,
  props.colSpan,
  props.rowSpan
);

onMounted(() => {
  grid.registerCallbacks(
    index,
    (dir) => emit('inner', dir),
    () => emit('confirm'),
    () => emit('cancel')
  );
});

defineExpose({ index });

const isSelected = computed(() => grid.selectedIndex.value === index);
const isActive = computed(() => grid.activeIndex.value === index);

const gridStyle = computed(() => ({
  gridColumn: `${props.col} / span ${props.colSpan}`,
  gridRow: `${props.row} / span ${props.rowSpan}`,
}));
</script>

<template>
  <div
    :style="gridStyle"
    :class="['panel-control', { selected: isSelected, active: isActive }]"
  >
    <slot :is-selected="isSelected" :is-active="isActive" />
  </div>
</template>

<style scoped lang="scss">
.panel-control {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid var(--panel-control-border, #444444);
  border-radius: 2px;
  background: var(--panel-control-bg, #000000);
  color: var(--panel-control-text, #ffffff);
  font-size: 11px;
  box-sizing: border-box;
  transition:
    border-color 0.05s,
    background 0.05s,
    color 0.05s;

  &.selected {
    border: 2px solid var(--panel-selected-border, #888888);
    background: var(--panel-selected-bg, #444444);
    color: var(--panel-selected-text, #ffffff);
  }

  &.active {
    border: 2px solid var(--panel-active-border, #888888);
    background: var(--panel-active-bg, #ffffff);
    color: var(--panel-active-text, #000000);
  }
}
</style>

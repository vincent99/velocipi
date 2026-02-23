<script setup lang="ts">
import { ref, computed, watch, inject, onMounted } from 'vue';
import PanelControl from '@/components/panel/PanelControl.vue';
import { PANEL_GRID_KEY } from '@/composables/usePanelGrid';
import type { PanelGridContext } from '@/composables/usePanelGrid';

export interface SelectOption {
  name: string;
  value: string;
  icon?: string; // uicons class suffix e.g. "camera-viewfinder"
}

const props = withDefaults(
  defineProps<{
    col: number;
    row: number;
    colSpan?: number;
    rowSpan?: number;
    options: SelectOption[];
    modelValue: string;
  }>(),
  { colSpan: 1, rowSpan: 1 }
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

const grid = inject<PanelGridContext>(PANEL_GRID_KEY);

// pendingIndex tracks the in-progress selection while active.
const pendingIndex = ref(0);
// controlIndex is set once PanelControl registers itself (via its own inject).
// We need to know it to check whether *this* control is active before syncing.
// We read it reactively from grid.activeIndex by checking equality with our slot.
// Since PanelControl registers sequentially, we capture the index at first watch tick.
let myIndex: number | null = null;

function indexOfValue(val: string): number {
  const i = props.options.findIndex((o) => o.value === val);
  return i >= 0 ? i : 0;
}

function isThisControlActive(): boolean {
  if (!grid || myIndex === null) {
    return false;
  }
  return grid.activeIndex.value === myIndex;
}

// Only sync pendingIndex from modelValue when this control is NOT active.
watch(
  () => props.modelValue,
  (val) => {
    if (!isThisControlActive()) {
      pendingIndex.value = indexOfValue(val);
    }
  },
  { immediate: true }
);

// Initialise pendingIndex immediately.
pendingIndex.value = indexOfValue(props.modelValue);

const displayOption = computed(() => props.options[pendingIndex.value]);

// tall: rowSpan >= 2 → stack icon above label
const tall = computed(() => (props.rowSpan ?? 1) >= 2);

function onInner(dir: 'left' | 'right') {
  const len = props.options.length;
  if (len === 0) {
    return;
  }
  if (dir === 'left') {
    pendingIndex.value = (pendingIndex.value - 1 + len) % len;
  } else {
    pendingIndex.value = (pendingIndex.value + 1) % len;
  }
}

function onConfirm() {
  const opt = props.options[pendingIndex.value];
  if (opt) {
    emit('update:modelValue', opt.value);
  }
}

function onCancel() {
  pendingIndex.value = indexOfValue(props.modelValue);
}

// Capture this control's index from the grid after PanelControl registers.
// PanelControl calls registerControl() synchronously in setup, so the next
// registered index is controlCount before our child mounts.
// Easiest: watch activeIndex changes and identify ourselves by slot reactivity —
// but simpler: expose a callback from PanelControl. Instead we sniff the index
// by watching the grid's controlCount at the time our child mounts.
// We use a ref that PanelControl populates via an exposed value.
const controlRef = ref<InstanceType<typeof PanelControl> | null>(null);

// PanelControl exposes its index via defineExpose — we read it after mount.
onMounted(() => {
  if (controlRef.value) {
    myIndex = (controlRef.value as unknown as { index: number }).index;
  }
});
</script>

<template>
  <PanelControl
    ref="controlRef"
    :col="col"
    :row="row"
    :col-span="colSpan"
    :row-span="rowSpan"
    @inner="onInner"
    @confirm="onConfirm"
    @cancel="onCancel"
  >
    <template #default>
      <span v-if="displayOption" :class="['select-content', { tall }]">
        <i
          v-if="displayOption.icon"
          :class="`fi-sr-${displayOption.icon}`"
          class="select-icon"
        />
        <span class="select-name">{{ displayOption.name }}</span>
      </span>
      <span v-else class="select-empty">—</span>
    </template>
  </PanelControl>
</template>

<style scoped lang="scss">
.select-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  overflow: hidden;
  max-width: 100%;
  max-height: 100%;

  &.tall {
    flex-direction: column;
  }
}

.select-icon {
  font-size: 12px;
  flex-shrink: 0;
  line-height: 1;
}

.select-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  line-height: 1;
}

.select-empty {
  opacity: 0.4;
}
</style>

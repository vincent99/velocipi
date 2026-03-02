<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useConfig } from '@/composables/useConfig';

export interface ActionItem {
  key: string;
  label: string;
  icon?: string;
}

const props = defineProps<{ items: ActionItem[] }>();
const emit = defineEmits<{ select: [key: string] }>();

const { config } = useConfig();
const visible = ref(false);
const selectedIndex = ref(0);
let hideTimer: ReturnType<typeof setTimeout> | null = null;
const cellWidth = computed(() => config.value?.navMenu.cellWidth ?? 64);

function resetTimer() {
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
  }
  hideTimer = setTimeout(() => {
    visible.value = false;
    hideTimer = null;
  }, config.value?.navMenu.hideDelay ?? 2000);
}

function show() {
  selectedIndex.value = 0;
  visible.value = true;
  resetTimer();
}

function onKeyDown(e: KeyboardEvent) {
  if (!visible.value) {
    return;
  }
  const km = config.value?.keyMap;
  if (!km) {
    return;
  }

  if (e.key === km.innerLeft) {
    e.stopImmediatePropagation();
    e.preventDefault();
    selectedIndex.value = Math.max(0, selectedIndex.value - 1);
    resetTimer();
    return;
  }

  if (e.key === km.innerRight) {
    e.stopImmediatePropagation();
    e.preventDefault();
    selectedIndex.value = Math.min(
      props.items.length - 1,
      selectedIndex.value + 1
    );
    resetTimer();
    return;
  }

  if (e.key === km.enter) {
    e.stopImmediatePropagation();
    e.preventDefault();
    const item = props.items[selectedIndex.value];
    if (item) {
      emit('select', item.key);
    }
    visible.value = false;
    if (hideTimer !== null) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    return;
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown, { capture: true });
});

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown, { capture: true });
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
  }
});

defineExpose({ show });
</script>

<template>
  <div v-if="visible" class="action-menu-overlay">
    <div class="action-dim" />
    <div class="action-bar">
      <div
        class="action-strip"
        :style="{ width: `${items.length * cellWidth}px` }"
      >
        <div
          v-for="(item, i) in items"
          :key="item.key"
          :class="['action-cell', { selected: i === selectedIndex }]"
          :style="{ width: `${cellWidth}px` }"
        >
          <span v-if="item.icon" class="action-icon">{{ item.icon }}</span>
          <span class="action-label">{{ item.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.action-menu-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  pointer-events: none;
}

.action-dim {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
}

.action-bar {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  height: 16px;
  background: #000;
  overflow: hidden;
  display: flex;
  align-items: center;
}

.action-strip {
  display: flex;
  height: 100%;
}

.action-cell {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: #fff;
  font-size: 10px;
  padding: 0 2px;

  &.selected {
    background: #fff;
    color: #000;
  }
}

.action-icon {
  font-size: 10px;
}

.action-label {
  white-space: nowrap;
  overflow: hidden;
}
</style>

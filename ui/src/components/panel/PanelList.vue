<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useConfig } from '@/composables/useConfig';
import ScrollingText from './ScrollingText.vue';

export interface ListItem {
  label: string;
  secondary?: string;
  icon?: string;
}

const props = defineProps<{
  items: ListItem[];
  modelValue?: number; // selected index; -1 = header row
  image?: string;
  headerLabel?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [index: number];
  select: [index: number];
  action: [index: number];
  'header-action': [];
  back: [];
  'to-now-playing': [];
}>();

const { config } = useConfig();
const longPressMs = computed(() => config.value?.navMenu.longPressMs ?? 1000);

const ROW_H = 16;
const hasHeader = computed(() => !!props.headerLabel);
const visibleRows = computed(() => (hasHeader.value ? 3 : 4));

const selectedIndex = ref(props.modelValue ?? 0);

watch(
  () => props.modelValue,
  (v) => {
    if (v !== undefined) {
      selectedIndex.value = v;
    }
  }
);

watch(selectedIndex, (v) => {
  emit('update:modelValue', v);
});

// Scroll offset: keep the selected row visible, centered in the viewport.
const offset = computed(() => {
  if (selectedIndex.value < 0) {
    return 0;
  }
  const pivot = Math.floor(visibleRows.value / 2);
  const maxOffset = Math.max(0, props.items.length - visibleRows.value) * ROW_H;
  return Math.min(Math.max(0, selectedIndex.value - pivot) * ROW_H, maxOffset);
});

// Long press tracking
let downTimer: ReturnType<typeof setTimeout> | null | -1 = null;
let upTimer: ReturnType<typeof setTimeout> | null | -1 = null;

function clearDownTimer() {
  if (downTimer !== null && downTimer !== -1) {
    clearTimeout(downTimer);
  }
  downTimer = null;
}

function clearUpTimer() {
  if (upTimer !== null && upTimer !== -1) {
    clearTimeout(upTimer);
  }
  upTimer = null;
}

function onKeyDown(e: KeyboardEvent) {
  const km = config.value?.keyMap;
  if (!km) {
    return;
  }

  if (e.key === km.joyLeft) {
    e.stopImmediatePropagation();
    e.preventDefault();
    const minIdx = hasHeader.value ? -1 : 0;
    selectedIndex.value = Math.max(minIdx, selectedIndex.value - 1);
    return;
  }

  if (e.key === km.joyRight) {
    e.stopImmediatePropagation();
    e.preventDefault();
    selectedIndex.value = Math.min(
      props.items.length - 1,
      selectedIndex.value + 1
    );
    return;
  }

  if (e.key === km.down && downTimer === null) {
    e.stopImmediatePropagation();
    e.preventDefault();
    downTimer = setTimeout(() => {
      downTimer = -1;
      if (selectedIndex.value < 0) {
        emit('header-action');
      } else {
        emit('action', selectedIndex.value);
      }
    }, longPressMs.value);
    return;
  }

  if (e.key === km.up && upTimer === null) {
    e.stopImmediatePropagation();
    e.preventDefault();
    upTimer = setTimeout(() => {
      upTimer = -1;
      emit('to-now-playing');
    }, longPressMs.value);
    return;
  }
}

function onKeyUp(e: KeyboardEvent) {
  const km = config.value?.keyMap;
  if (!km) {
    return;
  }

  if (e.key === km.down) {
    e.stopImmediatePropagation();
    e.preventDefault();
    if (downTimer === -1) {
      downTimer = null;
    } else if (downTimer !== null) {
      clearDownTimer();
      if (selectedIndex.value < 0) {
        emit('header-action');
      } else {
        emit('select', selectedIndex.value);
      }
    }
    return;
  }

  if (e.key === km.up) {
    e.stopImmediatePropagation();
    e.preventDefault();
    if (upTimer === -1) {
      upTimer = null;
    } else if (upTimer !== null) {
      clearUpTimer();
      emit('back');
    }
    return;
  }
}

onMounted(() => {
  // Capture phase so PanelList intercepts before layout-level handlers
  document.addEventListener('keydown', onKeyDown, { capture: true });
  document.addEventListener('keyup', onKeyUp, { capture: true });
});

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown, { capture: true });
  document.removeEventListener('keyup', onKeyUp, { capture: true });
  clearDownTimer();
  clearUpTimer();
});
</script>

<template>
  <div class="panel-list">
    <img v-if="image" :src="image" class="list-image" alt="" />
    <div class="list-body">
      <div
        v-if="headerLabel"
        :class="['list-header', { selected: selectedIndex === -1 }]"
      >
        {{ headerLabel }}
      </div>
      <div class="list-viewport">
        <div
          class="list-track"
          :style="{
            transform: `translateY(-${offset}px)`,
            transition: 'transform 0.1s ease',
            height: `${items.length * 16}px`,
          }"
        >
          <div
            v-for="(item, i) in items"
            :key="i"
            :class="['list-row', { selected: i === selectedIndex }]"
          >
            <span class="row-icon">{{ item.icon ?? '' }}</span>
            <ScrollingText class="row-label" :text="item.label" />
            <span v-if="item.secondary" class="row-secondary">{{
              item.secondary
            }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.panel-list {
  display: flex;
  width: 100%;
  height: var(--panel-h, 64px);
  overflow: hidden;
}

.list-image {
  width: var(--panel-h, 64px);
  height: var(--panel-h, 64px);
  object-fit: cover;
  flex-shrink: 0;
  display: block;
}

.list-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.list-header {
  height: 16px;
  line-height: 16px;
  font-size: 10px;
  padding: 0 4px;
  color: #aaa;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;

  &.selected {
    background: #fff;
    color: #000;
  }
}

.list-viewport {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.list-track {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
}

.list-row {
  height: 16px;
  display: flex;
  align-items: center;
  font-size: 12px;
  color: #fff;

  &.selected {
    background: #fff;
    color: #000;

    .row-secondary {
      color: #000;
    }
  }
}

.row-icon {
  width: 16px;
  flex-shrink: 0;
  text-align: center;
  font-size: 10px;
}

.row-label {
  flex: 1;
  min-width: 0;
  height: 16px;
}

.row-secondary {
  width: 48px;
  flex-shrink: 0;
  text-align: right;
  font-size: 10px;
  padding-right: 2px;
  white-space: nowrap;
  overflow: hidden;
  color: #888;
}
</style>

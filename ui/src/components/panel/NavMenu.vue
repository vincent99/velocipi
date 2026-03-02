<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfig } from '@/composables/useConfig';
import { usePanelRoutes } from '@/composables/usePanelRoutes';
import type { PanelRoute } from '@/composables/usePanelRoutes';

const props = withDefaults(
  defineProps<{
    size?: 'small' | 'large';
    position?: 'top' | 'middle' | 'bottom';
    leftKey?: string;
    rightKey?: string;
    items?: PanelRoute[];
    hideDelay?: number;
    selectKey?: string;
    cancelKey?: string;
  }>(),
  {
    size: 'large',
    position: 'bottom',
    leftKey: undefined,
    rightKey: undefined,
    items: undefined,
    hideDelay: undefined,
    selectKey: undefined,
    cancelKey: undefined,
  }
);

const defaultPanels = usePanelRoutes();
const panels = computed(() => props.items ?? defaultPanels);

function isIconClass(icon: string | undefined): boolean {
  return (icon?.length ?? 0) > 1;
}
const route = useRoute();
const router = useRouter();
const { config } = useConfig();

const visible = ref(false);
const selectedIndex = ref(0);
const containerRef = ref<HTMLElement | null>(null);
let hideTimer: ReturnType<typeof setTimeout> | null = null;

const hideDelay = computed(
  () => props.hideDelay ?? config.value?.navMenu.hideDelay ?? 2000
);
const cellWidth = computed(() => config.value?.navMenu.cellWidth ?? 64);
const containerWidth = computed(
  () => containerRef.value?.offsetWidth ?? config.value?.panel.width ?? 256
);

const barHeight = computed(() => (props.size === 'small' ? 16 : 32));

const offset = computed(() => {
  const center =
    selectedIndex.value * cellWidth.value -
    (containerWidth.value / 2 - cellWidth.value / 2);
  const max = panels.value.length * cellWidth.value - containerWidth.value;
  return Math.max(0, Math.min(center, max));
});

const barStyle = computed(() => {
  const h = barHeight.value;
  const base = {
    height: `${h}px`,
    position: 'absolute' as const,
    left: '0',
    right: '0',
    overflow: 'hidden' as const,
    background: '#000',
    borderTop: props.size === 'large' ? '1px solid #333' : 'none',
  };
  if (props.position === 'top') {
    return { ...base, top: '0' };
  } else if (props.position === 'middle') {
    return { ...base, top: '50%', transform: 'translateY(-50%)' };
  } else {
    return { ...base, bottom: '0' };
  }
});

function resetTimer() {
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
  if (hideDelay.value === 0) {
    return;
  }
  hideTimer = setTimeout(() => {
    visible.value = false;
    hideTimer = null;
  }, hideDelay.value);
}

const navKeys = computed<Record<string, 'left' | 'right'>>(() => {
  const lk = props.leftKey ?? config.value?.keyMap.outerLeft ?? '[';
  const rk = props.rightKey ?? config.value?.keyMap.outerRight ?? ']';
  return { [lk]: 'left', [rk]: 'right' };
});

function show() {
  const currentIndex = panels.value.findIndex((p) => p.path === route.path);
  selectedIndex.value = currentIndex >= 0 ? currentIndex : 0;
  visible.value = true;
  resetTimer();
}

function closeMenu() {
  visible.value = false;
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
}

function onKeyDown(e: KeyboardEvent) {
  // Select/cancel keys only act when the menu is already visible.
  if (visible.value) {
    if (props.selectKey && e.key === props.selectKey) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const target = panels.value[selectedIndex.value];
      if (target) {
        router.push(target.path);
      }
      closeMenu();
      return;
    }
    if (props.cancelKey && e.key === props.cancelKey) {
      e.preventDefault();
      e.stopImmediatePropagation();
      closeMenu();
      return;
    }
  }

  const dir = navKeys.value[e.key];
  if (!dir) {
    return;
  }

  e.preventDefault();
  e.stopImmediatePropagation();

  if (!visible.value) {
    show();
    return;
  }

  if (dir === 'right') {
    selectedIndex.value = Math.min(
      selectedIndex.value + 1,
      panels.value.length - 1
    );
  } else {
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0);
  }

  // Without a selectKey, navigate immediately on every left/right press.
  if (!props.selectKey) {
    const target = panels.value[selectedIndex.value];
    if (target) {
      router.push(target.path);
    }
  }
  resetTimer();
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
  <div ref="containerRef" class="nav-anchor">
    <div v-if="visible" class="nav-overlay">
      <div class="nav-dim" />
      <div :style="barStyle">
        <div
          class="nav-strip"
          :style="{
            transform: `translateX(-${offset}px)`,
            width: `${panels.length * cellWidth}px`,
            height: '100%',
          }"
        >
          <div
            v-for="(p, i) in panels"
            :key="p.path"
            :class="[
              'nav-cell',
              { selected: i === selectedIndex },
              `size-${size}`,
            ]"
            :style="{ width: `${cellWidth}px` }"
          >
            <template v-if="size === 'large'">
              <span class="nav-icon">
                <i
                  v-if="isIconClass(p.icon)"
                  :class="`fi-${p.iconStyle}-${p.icon}`"
                />
                <template v-else>{{ p.icon }}</template>
              </span>
              <span class="nav-name">{{ p.name }}</span>
            </template>
            <span v-else class="nav-name-small">{{ p.name }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
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
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
}

.nav-strip {
  display: flex;
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

  &.selected {
    background: #fff;
    color: #000;
  }

  &.size-large {
    .nav-icon {
      font-size: 16px;
      line-height: 1;
      margin-top: 3px;
    }

    .nav-name {
      font-size: 14px;
      line-height: 1;
      margin-top: -6px;
    }
  }
}

.nav-name-small {
  font-size: 10px;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  padding: 0 2px;
}
</style>

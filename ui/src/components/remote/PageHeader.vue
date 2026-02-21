<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfig } from '@/composables/useConfig';
import { useRemoteRoutes } from '@/composables/useRemoteRoutes';
import ScreenViewer from '@/components/remote/ScreenViewer.vue';

const { config } = useConfig();
const routes = useRemoteRoutes();
const route = useRoute();
const router = useRouter();

const menuOpen = ref(false);
const navEl = ref<HTMLElement | null>(null);

function onDocClick(e: MouseEvent) {
  if (
    menuOpen.value &&
    navEl.value &&
    !navEl.value.contains(e.target as Node)
  ) {
    menuOpen.value = false;
  }
}

onMounted(() => document.addEventListener('click', onDocClick, true));
onUnmounted(() => document.removeEventListener('click', onDocClick, true));

const headerColor = computed(() => config.value?.headerColor ?? '#b91c1c');
const tail = computed(() => config.value?.tail ?? '');

const currentRoute = computed(
  () => routes.find((r) => r.path === route.path) ?? routes[0]
);

function navigate(path: string) {
  menuOpen.value = false;
  router.push(path);
}
</script>

<template>
  <header class="page-header" :style="{ background: headerColor }">
    <!-- Left: screen viewer (hidden on routes that opt out) -->
    <div v-if="currentRoute?.headerScreen" class="header-screen">
      <ScreenViewer />
    </div>

    <!-- Center: tail number -->
    <div class="header-tail">
      {{ tail }}
    </div>

    <!-- Right: hamburger menu -->
    <div ref="navEl" class="header-nav">
      <button class="hamburger" @click="menuOpen = !menuOpen">
        <span class="current-icon">
          <i
            v-if="currentRoute?.icon.length > 1"
            :class="`fi-sr-${currentRoute.icon}`"
          />
          <template v-else>{{ currentRoute?.icon }}</template>
        </span>
        <span class="hamburger-bottom">
          <span class="current-name">{{ currentRoute?.name }}</span>
          <i class="fi-sr-angle-down menu-arrow" :class="{ open: menuOpen }" />
        </span>
      </button>

      <div v-if="menuOpen" class="dropdown">
        <button
          v-for="r in routes"
          :key="r.path"
          class="dropdown-item"
          :class="{ active: r.path === route.path }"
          @click="navigate(r.path)"
        >
          <span class="item-icon">
            <i v-if="r.icon.length > 1" :class="`fi-sr-${r.icon}`" />
            <template v-else>{{ r.icon }}</template>
          </span>
          <span>{{ r.name }}</span>
        </button>
      </div>
    </div>
  </header>
</template>

<style scoped lang="scss">
.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  color: #fff;
  position: relative;
  box-sizing: border-box;
  height: calc(64px + 1rem); // panel height + vertical padding
}

.header-screen {
  flex-shrink: 0;
  line-height: 0; // prevent extra space below img
}

.header-tail {
  position: absolute;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  pointer-events: none;
}

.header-nav {
  flex-shrink: 0;
  position: relative;
  margin-left: auto;
}

.hamburger {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  color: #fff;
  padding: 0.4rem 0.75rem;
  cursor: pointer;
  white-space: nowrap;

  &:hover {
    background: rgba(0, 0, 0, 0.4);
  }
}

.current-icon {
  font-size: 1.3rem;
  line-height: 1;
}

.hamburger-bottom {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
}

.menu-arrow {
  font-size: 0.65rem;
  transition: transform 0.15s ease;

  &.open {
    transform: rotate(180deg);
  }
}

.dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  overflow: hidden;
  min-width: 160px;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  background: none;
  border: none;
  color: #eee;
  cursor: pointer;
  font-size: 0.9rem;
  text-align: left;

  &:hover {
    background: #2a2a2a;
  }

  &.active {
    background: #333;
    color: #fff;
    font-weight: 600;
  }
}

.item-icon {
  width: 1.2rem;
  text-align: center;
  flex-shrink: 0;
}
</style>

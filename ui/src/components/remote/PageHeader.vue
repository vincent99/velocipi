<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfig } from '@/composables/useConfig';
import { useRemoteRoutes } from '@/composables/useRemoteRoutes';
import { useCameraList } from '@/composables/useCameraList';
import ScreenViewer from '@/components/remote/ScreenViewer.vue';
import CameraThumbnail from '@/components/remote/CameraThumbnail.vue';

const { config } = useConfig();
const routes = useRemoteRoutes();
const route = useRoute();
const router = useRouter();
const { cameras } = useCameraList();

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

// Keep document title in sync with the tail number.
watch(
  tail,
  (t) => {
    document.title = t || 'velocipi';
  },
  { immediate: true }
);

const currentRoute = computed(
  () => routes.find((r) => r.path === route.path) ?? routes[0]
);

// The camera currently being viewed (from ?cam= query param on /cameras route).
const activeCam = computed(() =>
  route.path === '/remote/cameras' ? ((route.query.cam as string) ?? '') : ''
);

function navigate(path: string) {
  menuOpen.value = false;
  router.push(path);
}

function openCamera(name: string) {
  router.push({ path: '/remote/cameras', query: { cam: name } });
}
</script>

<template>
  <header class="page-header" :style="{ background: headerColor }">
    <!-- Screen viewer + camera thumbnails on the left, wrap together -->
    <div v-if="currentRoute?.headerScreen" class="header-left">
      <div class="header-screen">
        <ScreenViewer />
      </div>
    </div>
    <div v-if="cameras.length > 0" class="header-cameras">
      <CameraThumbnail
        v-for="cam in cameras"
        :key="cam"
        :name="cam"
        :selected="cam === activeCam"
        @select="openCamera"
      />
    </div>

    <!-- Right: hamburger menu, always last in flow -->
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
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  color: #fff;
  position: relative;
  box-sizing: border-box;
  // No fixed height — grows to fit if content wraps to a second row.
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.header-screen {
  flex-shrink: 0;
  line-height: 0; // prevent extra space below img
  height: 64px;
}

.header-cameras {
  display: flex;
  align-items: stretch;
  gap: 0.25rem;
  height: 64px;
  flex-wrap: wrap;
  flex-shrink: 1;
  min-width: 0;
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

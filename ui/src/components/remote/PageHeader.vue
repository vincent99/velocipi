<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfig } from '@/composables/useConfig';
import { useRemoteRoutes } from '@/composables/useRemoteRoutes';
import { useCameraList } from '@/composables/useCameraList';
import { useAdmin } from '@/composables/useAdmin';
import CameraThumbnail from '@/components/remote/CameraThumbnail.vue';

const { config } = useConfig();
const routes = useRemoteRoutes();
const route = useRoute();
const router = useRouter();
const { cameras } = useCameraList();
const { isAdmin } = useAdmin();

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

const headerColor = computed(() => {
  if (isAdmin && config.value?.adminHeaderColor) {
    return config.value.adminHeaderColor;
  }
  return config.value?.headerColor ?? '#b91c1c';
});
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
  menuOpen.value = false;
  router.push({ path: '/remote/cameras', query: { cam: name } });
}

// Merged item list for the box layout.
// - Routes with sort < 0 (Home) come first
// - Camera items slot in at sort = 0
// - Routes with sort >= 0 follow; /remote/cameras is excluded since cameras
//   are represented individually as live-thumbnail boxes
type HeaderItem =
  | { kind: 'route'; route: (typeof routes)[0] }
  | { kind: 'camera'; name: string };

const mergedItems = computed<HeaderItem[]>(() => {
  const before = routes.filter(
    (r) => r.path !== '/remote/cameras' && r.sort < 0
  );
  const after = routes.filter(
    (r) => r.path !== '/remote/cameras' && r.sort >= 0
  );
  return [
    ...before.map((r) => ({ kind: 'route' as const, route: r })),
    ...cameras.value.map((n) => ({ kind: 'camera' as const, name: n })),
    ...after.map((r) => ({ kind: 'route' as const, route: r })),
  ];
});
</script>

<template>
  <header class="page-header" :style="{ background: headerColor }">
    <!-- Wide layout: flat row of equal-sized boxes -->
    <div class="header-boxes">
      <template
        v-for="item in mergedItems"
        :key="item.kind === 'camera' ? 'cam:' + item.name : item.route.path"
      >
        <!-- Camera box -->
        <div
          v-if="item.kind === 'camera'"
          class="nav-box nav-box--camera"
          :class="{ active: item.name === activeCam }"
          @click="openCamera(item.name)"
        >
          <CameraThumbnail
            :name="item.name"
            :selected="item.name === activeCam"
          />
        </div>

        <!-- Route box -->
        <div
          v-else
          class="nav-box nav-box--route"
          :class="{ active: item.route.path === route.path }"
          @click="navigate(item.route.path)"
        >
          <span class="box-icon">
            <i
              v-if="item.route.icon.length > 1"
              :class="`fi-${item.route.iconStyle}-${item.route.icon}`"
            />
            <template v-else>{{ item.route.icon }}</template>
          </span>
          <span class="box-label">{{ item.route.name }}</span>
        </div>
      </template>

      <!-- Leave admin box -->
      <a
        v-if="isAdmin"
        href="/admin?off"
        class="nav-box nav-box--route nav-box--admin-off"
      >
        <span class="box-icon"><i class="fi-sr-exit" /></span>
        <span class="box-label">Leave admin</span>
      </a>
    </div>

    <!-- Small-screen layout: hamburger dropdown -->
    <div ref="navEl" class="header-nav">
      <button class="hamburger" @click="menuOpen = !menuOpen">
        <span class="current-icon">
          <i
            v-if="currentRoute?.icon.length > 1"
            :class="`fi-${currentRoute.iconStyle}-${currentRoute.icon}`"
          />
          <template v-else>{{ currentRoute?.icon }}</template>
        </span>
        <span class="hamburger-bottom">
          <span class="current-name">{{ currentRoute?.name }}</span>
          <i class="fi-sr-angle-down menu-arrow" :class="{ open: menuOpen }" />
        </span>
      </button>

      <div v-if="menuOpen" class="dropdown">
        <template
          v-for="item in mergedItems"
          :key="item.kind === 'camera' ? 'cam:' + item.name : item.route.path"
        >
          <!-- Camera box -->
          <div
            v-if="item.kind === 'camera'"
            class="nav-box nav-box--camera"
            :class="{ active: item.name === activeCam }"
            @click="openCamera(item.name)"
          >
            <CameraThumbnail
              :name="item.name"
              :selected="item.name === activeCam"
            />
          </div>

          <!-- Route box -->
          <div
            v-else
            class="nav-box nav-box--route"
            :class="{ active: item.route.path === route.path }"
            @click="navigate(item.route.path)"
          >
            <span class="box-icon">
              <i
                v-if="item.route.icon.length > 1"
                :class="`fi-${item.route.iconStyle}-${item.route.icon}`"
              />
              <template v-else>{{ item.route.icon }}</template>
            </span>
            <span class="box-label">{{ item.route.name }}</span>
          </div>
        </template>

        <!-- Leave admin box -->
        <a
          v-if="isAdmin"
          href="/admin?off"
          class="nav-box nav-box--route nav-box--admin-off"
        >
          <span class="box-icon"><i class="fi-sr-exit" /></span>
          <span class="box-label">Leave admin</span>
        </a>
      </div>
    </div>
  </header>
</template>

<style scoped lang="scss">
.page-header {
  display: flex;
  align-items: flex-start;
  padding: 0.5rem;
  color: #fff;
  position: relative;
  box-sizing: border-box;
  width: 100%;
}

// ── Wide layout: box grid ──────────────────────────────────────────────────

.header-boxes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  // Hidden on small screens
  @media (max-width: 767px) {
    display: none;
  }
}

.nav-box {
  // 16:9 aspect ratio at a fixed height of 64px → width ~114px
  height: 64px;
  aspect-ratio: 16 / 9;
  flex-shrink: 0;
  cursor: pointer;
  border-radius: 4px;
  overflow: hidden;
  box-sizing: border-box;
  text-decoration: none;

  &:hover {
    outline: 2px solid rgba(255, 255, 255, 0.5);
  }

  &.active {
    outline: 2px solid #fff;
  }
}

.nav-box--camera {
  // CameraThumbnail fills the box
  :deep(.cam-thumb) {
    width: 100%;
    height: 100%;
  }

  :deep(.thumb-img) {
    width: 100%;
    height: 100%;
    min-width: unset;
    object-fit: cover;
  }
}

.nav-box--route {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #fff;

  &:hover {
    background: rgba(0, 0, 0, 0.4);
  }

  &.active {
    background: rgba(255, 255, 255, 0.15);
  }
}

.nav-box--admin-off {
  border-color: rgba(248, 113, 113, 0.5);
  color: #f87171;

  &:hover {
    background: rgba(90, 26, 26, 0.5);
  }
}

.box-icon {
  font-size: 1.4rem;
  line-height: 1;
}

.box-label {
  font-size: 0.6rem;
  line-height: 1.1;
  text-align: center;
  padding: 0 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

// ── Small-screen layout: hamburger ────────────────────────────────────────

.header-nav {
  flex-shrink: 0;
  position: static;
  margin-left: auto;
  // Hidden on wide screens
  @media (min-width: 768px) {
    display: none;
  }
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
  background: #111;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.5rem;
  display: grid;
  grid-template-columns: repeat(2, auto);
  gap: 0.5rem;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
}
</style>

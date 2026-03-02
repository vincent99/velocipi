<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const panelMeta: PanelMeta = {
  name: 'Music',
  icon: 'headphones',
  sort: 1,
};
</script>

<script setup lang="ts">
import { ref, computed, watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useConfig } from '@/composables/useConfig';
import { useDeviceState } from '@/composables/useDeviceState';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useMusicPanelKeys } from '@/composables/useMusicPanelKeys';
import NavMenu from '@/components/panel/NavMenu.vue';
import type { PanelRoute } from '@/composables/usePanelRoutes';

const route = useRoute();
const router = useRouter();
const { config } = useConfig();
const { musicState } = useDeviceState();
const player = useMusicPlayer();

const navMenuRef = ref<InstanceType<typeof NavMenu> | null>(null);

// Redirect bare /panel/music to now-playing
watchEffect(() => {
  if (route.path === '/panel/music') {
    router.replace('/panel/music/now-playing');
  }
});

const musicSubPages: PanelRoute[] = [
  { path: '/panel/music/queue', name: 'Queue', icon: 'list', iconStyle: 'sr' },
  { path: '/panel/music/songs', name: 'Songs', icon: 'music', iconStyle: 'sr' },
  {
    path: '/panel/music/artists',
    name: 'Artists',
    icon: 'user',
    iconStyle: 'sr',
  },
  {
    path: '/panel/music/albums',
    name: 'Albums',
    icon: 'album',
    iconStyle: 'sr',
  },
  {
    path: '/panel/music/genres',
    name: 'Genres',
    icon: 'guitar',
    iconStyle: 'sr',
  },
  {
    path: '/panel/music/decades',
    name: 'Decades',
    icon: 'calendar',
    iconStyle: 'sr',
  },
  {
    path: '/panel/music/playlists',
    name: 'Playlists',
    icon: 'playlist',
    iconStyle: 'sr',
  },
  {
    path: '/panel/music/smart-searches',
    name: 'Smart',
    icon: 'search',
    iconStyle: 'sr',
  },
];

const leftKey = computed(() => config.value?.keyMap.innerLeft ?? ';');
const rightKey = computed(() => config.value?.keyMap.innerRight ?? "'");
const selectKey = computed(() => config.value?.keyMap.down ?? 'ArrowDown');
const cancelKey = computed(() => config.value?.keyMap.up ?? 'ArrowUp');

useMusicPanelKeys({
  playPause() {
    if (musicState.value?.status === 'playing') {
      player.pause();
    } else {
      player.play();
    }
  },
  toNowPlaying() {
    router.push('/panel/music/now-playing');
  },
  openNav() {
    navMenuRef.value?.show();
  },
  prev() {
    player.prev();
  },
  seekBack() {
    player.skipBack(10);
  },
  next() {
    player.next();
  },
  seekForward() {
    player.skipForward(10);
  },
});
</script>

<template>
  <div class="music-layout">
    <RouterView />
    <NavMenu
      ref="navMenuRef"
      size="small"
      position="middle"
      :hide-delay="0"
      :left-key="leftKey"
      :right-key="rightKey"
      :select-key="selectKey"
      :cancel-key="cancelKey"
      :items="musicSubPages"
    />
  </div>
</template>

<style scoped>
.music-layout {
  position: relative;
  width: 100%;
  height: 100%;
}
</style>

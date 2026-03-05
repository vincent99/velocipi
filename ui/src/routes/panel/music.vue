<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const panelMeta: PanelMeta = {
  name: 'Music',
  icon: 'headphones',
  sort: 1,
};
</script>

<script setup lang="ts">
import { watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useDeviceState } from '@/composables/useDeviceState';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useMusicPanelKeys } from '@/composables/useMusicPanelKeys';

const route = useRoute();
const router = useRouter();
const { musicState } = useDeviceState();
const player = useMusicPlayer();

// Redirect bare /panel/music to now-playing
watchEffect(() => {
  if (route.path === '/panel/music') {
    router.replace('/panel/music/now-playing');
  }
});

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
  </div>
</template>

<style scoped>
.music-layout {
  position: relative;
  width: 100%;
  height: 100%;
}
</style>

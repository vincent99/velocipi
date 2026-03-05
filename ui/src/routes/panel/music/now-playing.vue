<script setup lang="ts">
import { ref, computed } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useConfig } from '@/composables/useConfig';
import ScrollingText from '@/components/panel/ScrollingText.vue';
import NavMenu from '@/components/panel/NavMenu.vue';
import type { PanelRoute } from '@/composables/usePanelRoutes';

const { musicState } = useDeviceState();
const { currentSong } = useMusicPlayer();
const { config } = useConfig();

const navMenuRef = ref<InstanceType<typeof NavMenu> | null>(null);

const musicSubPages: PanelRoute[] = [
  {
    path: '/panel/music/queue',
    name: 'Queue',
    sort: -3,
  },
  {
    path: '/panel/music/smart-searches',
    name: 'Smart',
    sort: -2,
  },
  {
    path: '/panel/music/playlists',
    name: 'Playlists',
    sort: -1,
  },
  {
    path: '/panel/music/artists',
    name: 'Artists',
    sort: 0,
  },
  {
    path: '/panel/music/albums',
    name: 'Albums',
    sort: 1,
  },
  {
    path: '/panel/music/songs',
    name: 'Songs',
    sort: 2,
  },
  {
    path: '/panel/music/genres',
    name: 'Genres',
    sort: 3,
  },
  {
    path: '/panel/music/decades',
    name: 'Decades',
    sort: 4,
  },
];

const navLeftKey = computed(() => [
  config.value?.keyMap.left ?? 'ArrowLeft',
  config.value?.keyMap.joyLeft ?? ',',
]);
const navRightKey = computed(() => [
  config.value?.keyMap.right ?? 'ArrowRight',
  config.value?.keyMap.joyRight ?? '.',
]);
const navSelectKey = computed(() => [
  config.value?.keyMap.down ?? 'ArrowDown',
  config.value?.keyMap.enter ?? 'Enter',
]);
const navCancelKey = computed(() => config.value?.keyMap.up ?? 'ArrowUp');
const navShowKey = computed(() => config.value?.keyMap.down ?? 'ArrowDown');

const artUrl = computed(() => {
  const id = currentSong.value?.coverId;
  return id != null ? `/music/cover/${id}` : null;
});

const statusIcon = computed(() => {
  const s = musicState.value?.status;
  if (s === 'playing') {
    return '▶';
  }
  if (s === 'paused') {
    return '⏸';
  }
  return '■';
});

const elapsedFormatted = computed(() =>
  formatTime(musicState.value?.elapsedSec ?? 0)
);

const remainingFormatted = computed(() => {
  const len = currentSong.value?.length ?? 0;
  const elapsed = musicState.value?.elapsedSec ?? 0;
  if (!len) {
    return '';
  }
  return `-${formatTime(Math.max(0, len - elapsed))}`;
});

const albumText = computed(() => {
  const song = currentSong.value;
  if (!song) {
    return '—';
  }
  return song.year ? `${song.album} (${song.year})` : song.album || '—';
});

const progressPct = computed(() => {
  const len = currentSong.value?.length ?? 0;
  const elapsed = musicState.value?.elapsedSec ?? 0;
  if (!len) {
    return 0;
  }
  return Math.min(1, elapsed / len) * 100;
});

const shuffleOn = computed(() => musicState.value?.shuffle ?? false);
const repeatMode = computed(() => musicState.value?.repeat ?? 'off');

const queuePos = computed(() => {
  const idx = musicState.value?.queueIndex ?? 0;
  const len = musicState.value?.queueLength ?? 0;
  if (!len) {
    return '';
  }
  return `${idx + 1}/${len}`;
});

function formatTime(sec: number): string {
  const total = Math.round(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}
</script>

<template>
  <div class="now-playing">
    <!-- Left: song info -->
    <div class="info-col">
      <div class="info-row">
        <ScrollingText :text="currentSong?.title ?? '—'" />
      </div>
      <div class="info-row">
        <ScrollingText :text="currentSong?.artist ?? '—'" />
      </div>
      <div class="info-row">
        <ScrollingText :text="albumText" />
      </div>

      <!-- Bottom row: status + time, repeat/shuffle/queue -->
      <div class="status-row">
        <span class="status-time"
          >{{ statusIcon }} {{ elapsedFormatted }}/{{
            remainingFormatted
          }}</span
        >
        <span class="status-right">
          <i v-if="shuffleOn" class="fi-sr-shuffle" />
          <i v-if="repeatMode === 'song'" class="fi-sr-arrows-repeat-1" />
          <i v-else-if="repeatMode === 'queue'" class="fi-sr-arrows-repeat" />
          {{ queuePos }}
        </span>
      </div>
    </div>

    <!-- Right: album art (64×64) -->
    <div class="art-col">
      <img v-if="artUrl" :src="artUrl" class="art-img" alt="" />
      <div v-else class="art-placeholder">♪</div>
    </div>

    <!-- Progress bar: absolute at bottom, spans left edge to art -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: `${progressPct}%` }" />
    </div>

    <NavMenu
      ref="navMenuRef"
      size="small"
      position="middle"
      :hide-delay="0"
      :show-key="navShowKey"
      :left-key="navLeftKey"
      :right-key="navRightKey"
      :select-key="navSelectKey"
      :cancel-key="navCancelKey"
      :items="musicSubPages"
    />
  </div>
</template>

<style scoped>
.now-playing {
  display: flex;
  position: relative;
  width: var(--panel-w, 256px);
  height: var(--panel-h, 64px);
  overflow: hidden;
  color: #fff;
  font-size: 12px;
}

.info-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding-left: 2px;
  padding-right: 4px;
}

.info-row {
  height: 16px;
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
}

.status-row {
  height: 16px;
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  overflow: hidden;
}

.status-time {
  font-size: 10px;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.status-right {
  font-size: 10px;
  white-space: nowrap;
  flex-shrink: 0;
  text-align: right;
  padding-right: 2px;
}

.art-col {
  width: var(--panel-h, 64px);
  height: var(--panel-h, 64px);
  flex-shrink: 0;
  background: #111;
  display: flex;
  align-items: center;
  justify-content: center;
}

.art-img {
  width: var(--panel-h, 64px);
  height: var(--panel-h, 64px);
  object-fit: cover;
  display: block;
}

.art-placeholder {
  font-size: 24px;
  color: #444;
}

.progress-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: var(--panel-h, 64px);
  height: 2px;
  background: #333;
}

.progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: #fff;
  transition: width 0.5s linear;
}
</style>

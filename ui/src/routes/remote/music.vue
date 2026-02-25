<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Music',
  icon: 'music',
  sort: 10,
};
</script>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router';
import { useMusicPlayer } from '@/composables/useMusicPlayer';

const route = useRoute();
const router = useRouter();

const {
  musicState,
  currentSong,
  play,
  pause,
  next,
  prev,
  seek,
  setShuffle,
  setRepeat,
} = useMusicPlayer();

// Redirect /remote/music → /remote/music/songs
watch(
  () => route.path,
  (path) => {
    if (path === '/remote/music') {
      router.replace('/remote/music/songs');
    }
  },
  { immediate: true }
);

const isPlaying = computed(() => musicState.value?.status === 'playing');

const elapsed = computed(() => musicState.value?.elapsedSec ?? 0);
const duration = computed(() => currentSong.value?.length ?? 0);

const shuffle = computed(() => musicState.value?.shuffle ?? false);
const repeat = computed(() => musicState.value?.repeat ?? 'off');

function formatTime(sec: number): string {
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${m}:${ss.toString().padStart(2, '0')}`;
}

function togglePlayPause() {
  if (isPlaying.value) {
    pause();
  } else {
    play();
  }
}

function cycleRepeat() {
  const modes = ['off', 'song', 'queue'] as const;
  const idx = modes.indexOf(repeat.value as 'off' | 'song' | 'queue');
  setRepeat(modes[(idx + 1) % modes.length]);
}

function onSeek(event: Event) {
  const input = event.target as HTMLInputElement;
  seek(parseFloat(input.value));
}

// Right sidebar tabs
const rightTab = ref<'queue' | 'playlists'>('queue');

// Nav links
const navLinks = [
  { to: '/remote/music/songs', label: 'Songs' },
  { to: '/remote/music/albums', label: 'Albums' },
  { to: '/remote/music/artists', label: 'Artists' },
  { to: '/remote/music/genres', label: 'Genres' },
  { to: '/remote/music/decades', label: 'Decades' },
];
</script>

<template>
  <div class="music-layout">
    <!-- Header: now-playing + controls -->
    <div class="music-header">
      <div class="now-playing">
        <img
          v-if="currentSong?.coverId"
          :src="`/music/cover/${currentSong.coverId}`"
          class="header-thumb"
          alt=""
        />
        <div v-else class="header-thumb-placeholder"></div>
        <div class="now-playing-info">
          <div class="now-playing-title">{{ currentSong?.title || '—' }}</div>
          <div class="now-playing-artist">{{ currentSong?.artist || '' }}</div>
        </div>
      </div>

      <div class="transport">
        <button
          class="ctrl-btn"
          :class="{ active: shuffle }"
          title="Shuffle"
          @click="setShuffle(!shuffle)"
        >
          ⇌
        </button>
        <button class="ctrl-btn" title="Previous" @click="prev">⏮</button>
        <button
          class="ctrl-btn ctrl-btn--main"
          :title="isPlaying ? 'Pause' : 'Play'"
          @click="togglePlayPause"
        >
          {{ isPlaying ? '⏸' : '▶' }}
        </button>
        <button class="ctrl-btn" title="Next" @click="next">⏭</button>
        <button
          class="ctrl-btn ctrl-btn--repeat"
          :class="{ active: repeat !== 'off' }"
          title="Repeat"
          @click="cycleRepeat"
        >
          {{ repeat === 'song' ? '🔂' : '🔁' }}
        </button>
      </div>

      <div class="progress-area">
        <span class="time-label">{{ formatTime(elapsed) }}</span>
        <input
          type="range"
          class="progress-bar"
          :value="elapsed"
          :max="duration || 1"
          step="1"
          @change="onSeek"
        />
        <span class="time-label">{{ formatTime(duration) }}</span>
      </div>
    </div>

    <!-- Body -->
    <div class="music-body">
      <!-- Left nav -->
      <nav class="music-nav">
        <RouterLink
          v-for="link in navLinks"
          :key="link.to"
          :to="link.to"
          class="nav-link"
          active-class="nav-link--active"
        >
          {{ link.label }}
        </RouterLink>
      </nav>

      <!-- Content -->
      <div class="music-content">
        <RouterView />
      </div>

      <!-- Right: queue / playlists -->
      <div class="music-sidebar-right">
        <div class="sidebar-tabs">
          <button
            :class="{ active: rightTab === 'queue' }"
            @click="rightTab = 'queue'"
          >
            Queue
          </button>
          <button
            :class="{ active: rightTab === 'playlists' }"
            @click="rightTab = 'playlists'"
          >
            Playlists
          </button>
        </div>
        <div v-if="rightTab === 'queue'" class="queue-list">
          <div
            v-if="!musicState || musicState.queueLength === 0"
            class="queue-empty"
          >
            Queue is empty
          </div>
          <div v-else class="queue-count">
            {{ musicState.queueLength }} song{{
              musicState.queueLength === 1 ? '' : 's'
            }}
          </div>
        </div>
        <div v-else class="playlists-panel">
          <div class="queue-empty">Playlists coming soon</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.music-layout {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: #111;
  color: #e0e0e0;
  overflow: hidden;
}

.music-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.now-playing {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 180px;
  flex: 0 0 auto;
}

.header-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}

.header-thumb-placeholder {
  width: 48px;
  height: 48px;
  background: #333;
  border-radius: 4px;
  flex-shrink: 0;
}

.now-playing-info {
  min-width: 0;
}

.now-playing-title {
  font-weight: 600;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.now-playing-artist {
  font-size: 0.78rem;
  color: #aaa;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.transport {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex: 0 0 auto;
}

.ctrl-btn {
  background: none;
  border: 1px solid transparent;
  color: #ccc;
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: #2a2a2a;
    color: #fff;
  }

  &.active {
    color: #3b82f6;
  }

  &--main {
    font-size: 1.2rem;
    padding: 0.3rem 0.75rem;
    background: #1e3a5f;
    color: #90caf9;
    border-color: #2a5a9f;

    &:hover {
      background: #2a4a7f;
    }
  }
}

.progress-area {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1 1 200px;
  min-width: 120px;
}

.time-label {
  font-size: 0.78rem;
  color: #888;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.progress-bar {
  flex: 1;
  height: 4px;
  appearance: none;
  background: #333;
  border-radius: 2px;
  cursor: pointer;
  outline: none;

  &::-webkit-slider-thumb {
    appearance: none;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #3b82f6;
    cursor: pointer;
  }
}

.music-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.music-nav {
  display: flex;
  flex-direction: column;
  width: 110px;
  flex-shrink: 0;
  background: #161616;
  border-right: 1px solid #2a2a2a;
  padding: 0.5rem 0;
  overflow-y: auto;
}

.nav-link {
  display: block;
  padding: 0.5rem 1rem;
  color: #aaa;
  text-decoration: none;
  font-size: 0.85rem;
  transition:
    background 0.15s,
    color 0.15s;

  &:hover {
    background: #222;
    color: #e0e0e0;
  }

  &--active {
    background: #1e3a5f;
    color: #90caf9;
  }
}

.music-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.music-sidebar-right {
  width: 200px;
  flex-shrink: 0;
  background: #161616;
  border-left: 1px solid #2a2a2a;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.sidebar-tabs {
  display: flex;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;

  button {
    flex: 1;
    background: none;
    border: none;
    color: #888;
    padding: 0.4rem;
    font-size: 0.78rem;
    cursor: pointer;
    transition:
      background 0.15s,
      color 0.15s;

    &:hover {
      background: #222;
      color: #ccc;
    }

    &.active {
      color: #90caf9;
      border-bottom: 2px solid #3b82f6;
    }
  }
}

.queue-list,
.playlists-panel {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.queue-empty {
  color: #555;
  font-size: 0.8rem;
  text-align: center;
  padding: 1rem 0;
}

.queue-count {
  color: #888;
  font-size: 0.8rem;
  text-align: center;
  padding: 0.5rem 0;
}
</style>

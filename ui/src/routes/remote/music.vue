<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Music',
  icon: 'music',
  sort: 10,
};
</script>

<script setup lang="ts">
import { ref, computed, watch, provide } from 'vue';
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useLocalPref } from '@/composables/useLocalPreferences';
import { useSongEdit } from '@/composables/useSongEdit';
import { useLyrics } from '@/composables/useLyrics';
import SongEditModal from '@/components/remote/music/SongEditModal.vue';
import SongFlagButtons from '@/components/remote/music/SongFlagButtons.vue';
import MusicNav from '@/components/remote/music/MusicNav.vue';
import QueueSidebar from '@/components/remote/music/QueueSidebar.vue';
import CreatePlaylistModal from '@/components/remote/music/CreatePlaylistModal.vue';
import CreateSmartSearchModal from '@/components/remote/music/CreateSmartSearchModal.vue';
import type { Playlist, SmartSearch } from '@/types/music';

const route = useRoute();
const router = useRouter();

// Initialize lyrics singleton so it starts tracking the current song.
useLyrics();

// Mobile-only UI state
const mobileNavOpen = ref(false);
const mobileQueueOpen = ref(false);

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

const { editingSongs, saving: editSaving, closeEdit, saveEdit } = useSongEdit();

// Resizable sidebar widths — persisted in localStorage
const navWidth = useLocalPref('music.navWidth', 110);
const sidebarWidth = useLocalPref('music.sidebarWidth', 200);

function startResize(side: 'left' | 'right', e: MouseEvent | TouchEvent) {
  e.preventDefault();
  const startX = 'touches' in e ? e.touches[0].clientX : e.clientX;
  const startWidth = side === 'left' ? navWidth.value : sidebarWidth.value;

  function onMove(ev: MouseEvent | TouchEvent) {
    const x = 'touches' in ev ? ev.touches[0].clientX : ev.clientX;
    const delta = x - startX;
    const newW = Math.max(
      60,
      Math.min(320, startWidth + (side === 'left' ? delta : -delta))
    );
    if (side === 'left') {
      navWidth.value = newW;
    } else {
      sidebarWidth.value = newW;
    }
  }

  function onUp() {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('touchmove', onMove);
    window.removeEventListener('mouseup', onUp);
    window.removeEventListener('touchend', onUp);
  }

  window.addEventListener('mousemove', onMove);
  window.addEventListener('touchmove', onMove, { passive: false });
  window.addEventListener('mouseup', onUp);
  window.addEventListener('touchend', onUp);
}

// Redirect /remote/music → /remote/music/songs; also close mobile nav on any nav
watch(
  () => route.path,
  (path) => {
    if (path === '/remote/music') {
      router.replace('/remote/music/songs');
    }
    mobileNavOpen.value = false;
  },
  { immediate: true }
);

const isPlaying = computed(() => musicState.value?.status === 'playing');

const elapsed = computed(() => musicState.value?.elapsedSec ?? 0);
const duration = computed(() => currentSong.value?.length ?? 0);
const remaining = computed(() => {
  const rem = duration.value - elapsed.value;
  return rem > 0 ? rem : 0;
});

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

// ── Header search ─────────────────────────────────────────────────────────────

const baseNavLinks = [
  { to: '/remote/music/songs', label: 'Songs' },
  { to: '/remote/music/albums', label: 'Albums' },
  { to: '/remote/music/artists', label: 'Artists' },
  { to: '/remote/music/genres', label: 'Genres' },
  { to: '/remote/music/decades', label: 'Decades' },
];

const searchQuery = ref((route.query.q as string | undefined) ?? '');

watch(
  () => route.query.q as string | undefined,
  (q) => {
    searchQuery.value = q ?? '';
  }
);

const navLinks = computed(() => {
  const links = [...baseNavLinks];
  if (searchQuery.value.trim() || route.path === '/remote/music/search') {
    links.push({ to: '/remote/music/search', label: 'Search' });
  }
  return links;
});

function submitSearch() {
  const q = searchQuery.value.trim();
  if (!q) {
    return;
  }
  router.push({ path: '/remote/music/search', query: { q } });
}

// ── Playlists / Smart searches ─────────────────────────────────────────────────

const playlists = ref<Playlist[]>([]);
const smartSearches = ref<SmartSearch[]>([]);

async function loadPlaylists() {
  const [plRes, spRes] = await Promise.all([
    fetch('/music/playlists'),
    fetch('/music/smartsearches'),
  ]);
  if (plRes.ok) {
    playlists.value = await plRes.json();
  }
  if (spRes.ok) {
    smartSearches.value = await spRes.json();
  }
}

loadPlaylists();
provide('reloadPlaylists', loadPlaylists);

const showCreatePlaylist = ref(false);
const showCreateSmartSearch = ref(false);

async function handleDropOntoPlaylist(playlistId: number, songIds: number[]) {
  const pl = playlists.value.find((p) => p.id === playlistId);
  if (!pl) {
    return;
  }
  const newItems = [...pl.items, ...songIds];
  await fetch(`/music/playlists/${playlistId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: pl.name, items: newItems }),
  });
  pl.items = newItems;
}
</script>

<template>
  <div class="music-layout">
    <!-- Header: controls + now-playing + progress -->
    <div class="music-header">
      <div class="controls-column">
        <div class="transport">
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
            class="ctrl-btn"
            :class="shuffle ? 'active' : 'dimmed'"
            title="Shuffle"
            @click="setShuffle(!shuffle)"
          >
            <i class="fi-sr-shuffle" />
          </button>
          <button
            class="ctrl-btn"
            :class="repeat !== 'off' ? 'active' : 'dimmed'"
            title="Repeat"
            @click="cycleRepeat"
          >
            <i
              :class="
                repeat === 'song'
                  ? 'fi-sr-arrows-repeat-1'
                  : 'fi-sr-arrows-repeat'
              "
            />
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
          <span class="time-label">-{{ formatTime(remaining) }}</span>
        </div>
      </div>

      <div class="now-playing">
        <img
          v-if="currentSong?.coverId"
          :src="`/music/cover/${currentSong.coverId}`"
          class="header-thumb"
          alt=""
        />
        <div v-else class="header-thumb-placeholder"></div>
        <div class="now-playing-info">
          <div class="now-playing-title">
            <RouterLink
              v-if="currentSong?.album && currentSong?.artist"
              :to="{
                path: '/remote/music/albums',
                query: { artist: currentSong.artist, album: currentSong.album },
              }"
              class="np-link"
              >{{ currentSong.title || '—' }}</RouterLink
            >
            <template v-else>{{ currentSong?.title || '—' }}</template>
            <SongFlagButtons
              v-if="currentSong"
              :song="currentSong"
              variant="header"
            />
          </div>
          <div class="now-playing-sub">
            <RouterLink
              v-if="currentSong?.artist"
              :to="{
                path: '/remote/music/artists',
                query: { artist: currentSong.artist },
              }"
              class="np-link"
              >{{ currentSong.artist }}</RouterLink
            >
            <template v-if="currentSong?.album">
              <span class="np-sep">—</span>
              <RouterLink
                :to="{
                  path: '/remote/music/albums',
                  query: {
                    artist: currentSong.artist,
                    album: currentSong.album,
                  },
                }"
                class="np-link"
                >{{ currentSong.album }}</RouterLink
              >
            </template>
            <template v-if="currentSong?.year">
              <span class="np-sep">—</span>
              <span class="np-year">{{ currentSong.year }}</span>
            </template>
          </div>
        </div>
      </div>

      <div class="header-search-row">
        <button
          class="ctrl-btn mobile-nav-btn"
          :class="{ active: mobileNavOpen }"
          title="Navigation"
          @click="mobileNavOpen = !mobileNavOpen"
        >
          ☰
        </button>
        <!-- Sort controls are teleported here by SongTable on mobile -->
        <div id="mobile-sort-portal" class="mobile-sort-portal"></div>
        <form class="header-search" @submit.prevent="submitSearch">
          <input
            v-model="searchQuery"
            type="search"
            class="header-search-input"
            placeholder="Search…"
          />
        </form>
        <button
          class="ctrl-btn mobile-queue-btn"
          :class="{ active: mobileQueueOpen }"
          title="Queue"
          @click="mobileQueueOpen = !mobileQueueOpen"
        >
          <i class="fi-sr-list-music" />
        </button>
      </div>
    </div>

    <!-- Body -->
    <div class="music-body">
      <!-- Mobile backdrop: closes nav/queue when tapped -->
      <div
        class="mobile-backdrop"
        :class="{ visible: mobileNavOpen || mobileQueueOpen }"
        @click="
          mobileNavOpen = false;
          mobileQueueOpen = false;
        "
      />

      <!-- Left nav -->
      <MusicNav
        :width="navWidth"
        :mobile-open="mobileNavOpen"
        :nav-links="navLinks"
        :playlists="playlists"
        :smart-searches="smartSearches"
        @create-playlist="showCreatePlaylist = true"
        @create-smart-search="showCreateSmartSearch = true"
        @drop-onto-playlist="handleDropOntoPlaylist"
      />

      <!-- Left resize handle -->
      <div
        class="resize-handle"
        @mousedown.prevent="startResize('left', $event)"
        @touchstart.prevent="startResize('left', $event)"
      />

      <!-- Content -->
      <div class="music-content">
        <RouterView />
      </div>

      <!-- Right resize handle -->
      <div
        class="resize-handle"
        @mousedown.prevent="startResize('right', $event)"
        @touchstart.prevent="startResize('right', $event)"
      />

      <!-- Right: queue / lyrics sidebar -->
      <QueueSidebar
        :width="sidebarWidth"
        :mobile-open="mobileQueueOpen"
        @close="mobileQueueOpen = false"
      />
    </div>
  </div>

  <SongEditModal
    v-if="editingSongs.length > 0"
    :songs="editingSongs"
    :saving="editSaving"
    @save="saveEdit"
    @cancel="closeEdit"
  />

  <CreatePlaylistModal
    v-model:show="showCreatePlaylist"
    @created="loadPlaylists"
  />

  <CreateSmartSearchModal
    v-model:show="showCreateSmartSearch"
    @created="loadPlaylists"
  />
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
  min-width: 0;
}

.now-playing {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
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
  flex: 1;
  min-width: 0;
}

.now-playing-title {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-weight: 600;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;

  > :first-child {
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 1;
    min-width: 0;
  }
}

.now-playing-sub {
  font-size: 0.78rem;
  color: #aaa;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.np-link {
  color: inherit;
  text-decoration: none;

  &:hover {
    text-decoration: underline;
    color: #90caf9;
  }
}

.np-sep {
  margin: 0 0.25rem;
  color: #666;
}

.np-year {
  color: #666;
}

.controls-column {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 0 0 auto;
}

.transport {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.ctrl-btn {
  background: none;
  border: 1px solid transparent;
  color: #ccc;
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  transition: background 0.15s;

  i {
    display: block;
  }

  &:hover {
    background: #2a2a2a;
    color: #fff;
  }

  &.active {
    color: #3b82f6;
  }

  &.dimmed {
    color: #555;
  }

  &--main {
    font-size: 1.2rem;
    padding: 0.3rem 0.75rem;
    background: #1e3a5f;
    color: #90caf9;
    border-color: #2a5a9f;

    &:hover {
      background: #2a4a7f;
      color: #fff;
    }
  }
}

.progress-area {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 180px;
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

.resize-handle {
  width: 5px;
  flex-shrink: 0;
  cursor: col-resize;
  background: #2a2a2a;
  transition: background 0.1s;
  touch-action: none;

  &:hover {
    background: #3b82f6;
  }
}

.music-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.header-search-row {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.mobile-nav-btn,
.mobile-queue-btn {
  display: none;
  flex-shrink: 0;
}

.mobile-sort-portal {
  display: none;
}

.mobile-backdrop {
  display: none;
}

.header-search {
  display: flex;
}

.header-search-input {
  background: #222;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.82rem;
  padding: 0.3rem 0.6rem;
  width: 160px;
  outline: none;

  &::placeholder {
    color: #666;
  }

  &:focus {
    border-color: #3b82f6;
  }
}

// ── Responsive ────────────────────────────────────────────────────────────────
$mobile-bp: 600px;

@media (max-width: $mobile-bp) {
  .music-header {
    flex-direction: column;
    align-items: stretch;
    gap: 0.4rem;
    padding: 0.5rem;
  }

  .controls-column {
    align-items: center;
  }

  .transport {
    justify-content: center;
  }

  .progress-area {
    min-width: unset;
    width: 100%;
  }

  .now-playing {
    flex: 0 0 auto;
    justify-content: center;
  }

  .header-search-row {
    width: 100%;
  }

  .header-search {
    flex: 1;
  }

  .header-search-input {
    width: 100%;
    box-sizing: border-box;
  }

  .mobile-nav-btn,
  .mobile-queue-btn {
    display: flex;
  }

  .mobile-sort-portal {
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }

  // Hide resize handles
  .resize-handle {
    display: none;
  }

  // music-body is the positioning context for the absolute panels
  .music-body {
    position: relative;
  }

  // Backdrop: dims content behind open panels
  .mobile-backdrop {
    display: block;
    position: absolute;
    inset: 0;
    z-index: 150;
    background: rgba(0, 0, 0, 0.5);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s;

    &.visible {
      opacity: 1;
      pointer-events: auto;
    }
  }
}
</style>

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
import { useLocalPref } from '@/composables/useLocalPreferences';
import { useSongEdit } from '@/composables/useSongEdit';
import { useDeviceState } from '@/composables/useDeviceState';
import QueueRow from '@/components/remote/QueueRow.vue';
import SongEditModal from '@/components/remote/SongEditModal.vue';

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
  appendQueue,
  removeFromQueue,
  jumpToIndex,
  moveInQueue,
} = useMusicPlayer();

const { editingSongs, saving: editSaving, closeEdit, saveEdit } = useSongEdit();
const { musicQueue } = useDeviceState();

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

// Right sidebar tabs
const rightTab = ref<'queue' | 'playlists'>('queue');

// Nav links — Search only shown when there is a query
const baseNavLinks = [
  { to: '/remote/music/songs', label: 'Songs' },
  { to: '/remote/music/albums', label: 'Albums' },
  { to: '/remote/music/artists', label: 'Artists' },
  { to: '/remote/music/genres', label: 'Genres' },
  { to: '/remote/music/decades', label: 'Decades' },
];

async function handleQueueRemove(queueIndex: number) {
  await removeFromQueue(queueIndex);
}

function handleQueuePlay(queueIndex: number) {
  jumpToIndex(queueIndex);
}

// ── Queue drag-and-drop ───────────────────────────────────────────────────────

interface DropTarget {
  index: number;
  position: 'above' | 'below';
}
const dropTarget = ref<DropTarget | null>(null);
const draggingQueueIndex = ref<number | null>(null);

function handleQueueDragStart(queueIndex: number) {
  draggingQueueIndex.value = queueIndex;
  dropTarget.value = null;
}

function handleQueueDragOver(queueIndex: number, position: 'above' | 'below') {
  dropTarget.value = { index: queueIndex, position };
}

function handleQueueDragEnd() {
  draggingQueueIndex.value = null;
  dropTarget.value = null;
}

async function handleQueueRowDrop(
  onto: number,
  position: 'above' | 'below',
  from: number
) {
  dropTarget.value = null;
  draggingQueueIndex.value = null;
  let toIndex = position === 'above' ? onto : onto + 1;
  // Adjust for removal of the source row
  if (from < toIndex) {
    toIndex--;
  }
  if (from !== toIndex) {
    await moveInQueue(from, toIndex);
  }
}

async function handleQueueSongsDrop(
  onto: number,
  position: 'above' | 'below',
  songIds: number[]
) {
  dropTarget.value = null;
  const insertAfter = position === 'above' ? onto - 1 : onto;
  await insertSongsAtQueuePosition(songIds, insertAfter);
}

// Handle drops onto the empty queue area (below all rows)
async function handleQueueListDrop(e: DragEvent) {
  e.preventDefault();
  dropTarget.value = null;
  const dt = e.dataTransfer;
  if (!dt) {
    return;
  }
  const songStr = dt.getData('application/x-song-ids');
  if (songStr !== '') {
    const songIds: number[] = JSON.parse(songStr);
    await appendQueue(songIds);
  }
}

function handleQueueListDragOver(e: DragEvent) {
  if (e.dataTransfer?.types.includes('application/x-song-ids')) {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'move';
    }
  }
}

// Insert songIds starting at afterIndex+1 by appending then moving into position.
async function insertSongsAtQueuePosition(
  songIds: number[],
  afterIndex: number
) {
  const totalBefore = musicQueue.value?.entries.length ?? 0;
  await appendQueue(songIds);
  const numNew = songIds.length;
  const totalAfterAppend = totalBefore + numNew;
  // Songs were appended at indices [totalAfterAppend-numNew .. totalAfterAppend-1].
  // Move them one by one to [afterIndex+1 .. afterIndex+numNew].
  // After moving song i to position afterIndex+1+i, the remaining songs are
  // still at the tail, but the tail start shifts by 1 each time.
  for (let i = 0; i < numNew; i++) {
    const fromIdx = totalAfterAppend - numNew + i;
    const toIdx = afterIndex + 1 + i;
    if (fromIdx !== toIdx) {
      await moveInQueue(fromIdx, toIdx);
    }
  }
}

// ── Header search ─────────────────────────────────────────────────────────────

// Local input value — initialised from route and kept in sync on submit
const searchQuery = ref((route.query.q as string | undefined) ?? '');

// Keep box in sync if the user navigates to search with a different query
watch(
  () => route.query.q as string | undefined,
  (q) => {
    searchQuery.value = q ?? '';
  }
);

const navLinks = computed(() => {
  const links = [...baseNavLinks];
  if (searchQuery.value.trim()) {
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

      <form class="header-search" @submit.prevent="submitSearch">
        <input
          v-model="searchQuery"
          type="search"
          class="header-search-input"
          placeholder="Search…"
        />
      </form>
    </div>

    <!-- Body -->
    <div class="music-body">
      <!-- Left nav -->
      <nav class="music-nav" :style="{ width: navWidth + 'px' }">
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

      <!-- Right: queue / playlists -->
      <div class="music-sidebar-right" :style="{ width: sidebarWidth + 'px' }">
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
            Playlist
          </button>
        </div>
        <div
          v-if="rightTab === 'queue'"
          class="queue-list"
          @dragover="handleQueueListDragOver"
          @drop="handleQueueListDrop"
        >
          <div
            v-if="!musicState || musicState.queueLength === 0"
            class="queue-empty"
          >
            Queue is empty
          </div>
          <template v-else-if="musicQueue">
            <QueueRow
              v-for="(entry, idx) in musicQueue.entries"
              :key="entry.songId + '-' + idx"
              :entry="entry"
              :queue-index="idx"
              :current-index="musicQueue.currentIndex"
              :drop-indicator="
                dropTarget?.index === idx ? dropTarget.position : null
              "
              @remove="handleQueueRemove"
              @play="handleQueuePlay"
              @drag-start="handleQueueDragStart"
              @drag-over="handleQueueDragOver"
              @drag-end="handleQueueDragEnd"
              @drop-queue="handleQueueRowDrop"
              @drop-songs="handleQueueSongsDrop"
            />
          </template>
          <div v-else class="queue-empty">Loading…</div>
        </div>
        <div v-else class="playlists-panel">
          <div class="queue-empty">Playlists coming soon</div>
        </div>
      </div>
    </div>
  </div>

  <SongEditModal
    v-if="editingSongs.length > 0"
    :songs="editingSongs"
    :saving="editSaving"
    @save="saveEdit"
    @cancel="closeEdit"
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
  font-weight: 600;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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

.music-nav {
  display: flex;
  flex-direction: column;
  // width set via inline style (useLocalPref)
  flex-shrink: 0;
  background: #161616;
  padding: 0.5rem 0;
  overflow-y: auto;
  min-width: 60px;
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
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.music-sidebar-right {
  // width set via inline style (useLocalPref)
  flex-shrink: 0;
  background: #161616;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  min-width: 60px;
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

.header-search {
  flex: 0 0 auto;
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
</style>

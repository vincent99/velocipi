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
import type { Playlist, SmartSearch } from '@/types/music';

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

// ── Playlists / Smart playlists ───────────────────────────────────────────────

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

// Create smart search modal
const showCreateSmartSearch = ref(false);
const newSmartSearchName = ref('');
const newSmartSearchQuery = ref('');
const creatingSmartSearch = ref(false);

async function createSmartSearch() {
  const name = newSmartSearchName.value.trim();
  const query = newSmartSearchQuery.value.trim();
  if (!name || !query) {
    return;
  }
  creatingSmartSearch.value = true;
  try {
    const r = await fetch('/music/smartsearches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, query }),
    });
    if (r.ok) {
      showCreateSmartSearch.value = false;
      newSmartSearchName.value = '';
      newSmartSearchQuery.value = '';
      await loadPlaylists();
    }
  } finally {
    creatingSmartSearch.value = false;
  }
}

// Create playlist modal
const showCreatePlaylist = ref(false);
const newPlaylistName = ref('');
const creatingPlaylist = ref(false);

async function createPlaylist() {
  const name = newPlaylistName.value.trim();
  if (!name) {
    return;
  }
  creatingPlaylist.value = true;
  try {
    const r = await fetch('/music/playlists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, items: [] }),
    });
    if (r.ok) {
      showCreatePlaylist.value = false;
      newPlaylistName.value = '';
      await loadPlaylists();
    }
  } finally {
    creatingPlaylist.value = false;
  }
}

// Drop songs onto a playlist name in the nav
const navDropTarget = ref<number | null>(null); // playlist id

function onNavDragOver(playlistId: number, e: DragEvent) {
  if (e.dataTransfer?.types.includes('application/x-song-ids')) {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy';
    }
    navDropTarget.value = playlistId;
  }
}

function onNavDragLeave() {
  navDropTarget.value = null;
}

async function onNavDrop(playlistId: number, e: DragEvent) {
  e.preventDefault();
  navDropTarget.value = null;
  const songStr = e.dataTransfer?.getData('application/x-song-ids');
  if (!songStr) {
    return;
  }
  const songIds: number[] = JSON.parse(songStr);
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

        <!-- Smart Searches section -->
        <div class="nav-section-label">
          Smart Searches
          <button
            class="nav-add-btn"
            title="New Smart Search"
            @click.stop="showCreateSmartSearch = true"
          >
            +
          </button>
        </div>
        <RouterLink
          v-for="sp in smartSearches"
          :key="'sp-' + sp.id"
          :to="{ path: '/remote/music/smartsearch', query: { id: sp.id } }"
          class="nav-link nav-link--playlist"
          active-class="nav-link--active"
        >
          {{ sp.name }}
        </RouterLink>
        <div v-if="smartSearches.length === 0" class="nav-empty">
          No smart searches
        </div>

        <!-- Playlists section -->
        <div class="nav-section-label">
          Playlists
          <button
            class="nav-add-btn"
            title="New Playlist"
            @click.stop="showCreatePlaylist = true"
          >
            +
          </button>
        </div>
        <div
          v-for="pl in playlists"
          :key="'pl-' + pl.id"
          class="nav-link-wrap"
          :class="{ 'nav-drop-target': navDropTarget === pl.id }"
          @dragover="onNavDragOver(pl.id, $event)"
          @dragleave="onNavDragLeave"
          @drop="onNavDrop(pl.id, $event)"
        >
          <RouterLink
            :to="{ path: '/remote/music/playlist', query: { id: pl.id } }"
            class="nav-link nav-link--playlist"
            active-class="nav-link--active"
          >
            {{ pl.name }}
          </RouterLink>
        </div>
        <div v-if="playlists.length === 0" class="nav-empty">No playlists</div>
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

      <!-- Right: queue -->
      <div class="music-sidebar-right" :style="{ width: sidebarWidth + 'px' }">
        <div class="sidebar-heading">Queue</div>
        <div
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

  <!-- Create Smart Search modal -->
  <Teleport to="body">
    <div
      v-if="showCreateSmartSearch"
      class="modal-overlay"
      @click.self="showCreateSmartSearch = false"
    >
      <div class="create-pl-modal create-pl-modal--wide">
        <div class="create-pl-title">New Smart Search</div>
        <input
          v-model="newSmartSearchName"
          class="create-pl-input"
          type="text"
          placeholder="Name"
          @keydown.esc="showCreateSmartSearch = false"
        />
        <textarea
          v-model="newSmartSearchQuery"
          class="create-pl-textarea"
          placeholder="WHERE clause, e.g. plays > 5"
          rows="3"
          spellcheck="false"
          @keydown.esc="showCreateSmartSearch = false"
        />
        <div class="create-sp-hint">
          <strong>Available fields:</strong>
          <code>title</code>, <code>artist</code>, <code>album</code>,
          <code>year</code>, <code>length</code> (seconds), <code>plays</code>,
          <code>marked</code> (0 or 1), <code>trackNumber</code>,
          <code>discNumber</code>, <code>format</code>,
          <code>bitrate</code> (kbps)<br />
          <strong>Examples:</strong>
          <code>plays &gt; 10</code> ·
          <code>length &gt; 300 AND year &gt;= 1990</code> ·
          <code>artist = 'Radiohead'</code> ·
          <code>marked = 1</code>
        </div>
        <div class="create-pl-actions">
          <button
            class="create-pl-cancel"
            @click="showCreateSmartSearch = false"
          >
            Cancel
          </button>
          <button
            class="create-pl-ok"
            :disabled="
              !newSmartSearchName.trim() ||
              !newSmartSearchQuery.trim() ||
              creatingSmartSearch
            "
            @click="createSmartSearch"
          >
            {{ creatingSmartSearch ? 'Creating…' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Create Playlist modal -->
  <Teleport to="body">
    <div
      v-if="showCreatePlaylist"
      class="modal-overlay"
      @click.self="showCreatePlaylist = false"
    >
      <div class="create-pl-modal">
        <div class="create-pl-title">New Playlist</div>
        <input
          v-model="newPlaylistName"
          class="create-pl-input"
          type="text"
          placeholder="Playlist name"
          autofocus
          @keydown.enter="createPlaylist"
          @keydown.esc="showCreatePlaylist = false"
        />
        <div class="create-pl-actions">
          <button class="create-pl-cancel" @click="showCreatePlaylist = false">
            Cancel
          </button>
          <button
            class="create-pl-ok"
            :disabled="!newPlaylistName.trim() || creatingPlaylist"
            @click="createPlaylist"
          >
            {{ creatingPlaylist ? 'Creating…' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
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

.sidebar-heading {
  padding: 0.4rem 0.75rem;
  font-size: 0.72rem;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.nav-section-label {
  display: flex;
  align-items: center;
  padding: 0.5rem 0.75rem 0.2rem;
  font-size: 0.68rem;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 0.25rem;
}

.nav-add-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0 0.2rem;
  border-radius: 3px;

  &:hover {
    background: #333;
    color: #ccc;
  }
}

.nav-link-wrap {
  &.nav-drop-target > .nav-link {
    background: #1a3a5f;
    color: #90caf9;
  }
}

.nav-link--playlist {
  padding-left: 1.25rem;
  font-size: 0.82rem;
}

.nav-empty {
  padding: 0.25rem 1.25rem;
  font-size: 0.78rem;
  color: #444;
  font-style: italic;
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

.queue-list {
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

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 600;
}

.create-pl-modal {
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  min-width: 280px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.7);
}

.create-pl-title {
  font-weight: 600;
  font-size: 0.95rem;
  margin-bottom: 0.75rem;
  color: #e0e0e0;
}

.create-pl-input {
  width: 100%;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.9rem;
  padding: 0.4rem 0.6rem;
  outline: none;
  box-sizing: border-box;

  &:focus {
    border-color: #3b82f6;
  }
}

.create-pl-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.create-pl-cancel {
  background: none;
  border: 1px solid #444;
  color: #aaa;
  border-radius: 4px;
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
  cursor: pointer;

  &:hover {
    background: #333;
    color: #ccc;
  }
}

.create-pl-ok {
  background: #1e3a5f;
  border: 1px solid #2a5a9f;
  color: #90caf9;
  border-radius: 4px;
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: #2a4a7f;
    color: #fff;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.create-pl-modal--wide {
  min-width: 380px;
  max-width: 520px;
  width: 90vw;
}

.create-pl-textarea {
  width: 100%;
  margin-top: 0.5rem;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.88rem;
  font-family: 'Roboto Mono', 'Consolas', monospace;
  padding: 0.4rem 0.6rem;
  outline: none;
  resize: vertical;
  box-sizing: border-box;

  &:focus {
    border-color: #3b82f6;
  }
}

.create-sp-hint {
  margin-top: 0.6rem;
  font-size: 0.75rem;
  color: #777;
  line-height: 1.5;

  strong {
    color: #999;
  }

  code {
    background: #333;
    border-radius: 3px;
    padding: 0.05em 0.3em;
    font-size: 0.85em;
    color: #c8c8c8;
    font-family: 'Roboto Mono', 'Consolas', monospace;
  }
}
</style>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { Song } from '@/types/music';

interface Props {
  songs: Song[];
  loading?: boolean;
  showAlbum?: boolean;
  groupByAlbum?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  showAlbum: true,
  groupByAlbum: false,
});

const emit = defineEmits<{
  enqueue: [ids: number[]];
  append: [ids: number[]];
  replace: [ids: number[]];
  mark: [ids: number[], marked: boolean];
}>();

// Selection state
const selectedIds = ref<Set<number>>(new Set());
const lastClickedIndex = ref<number>(-1);

// Context menu state
const contextMenu = ref<{ x: number; y: number; visible: boolean }>({
  x: 0,
  y: 0,
  visible: false,
});

// Touch drag selection
const touchStartIndex = ref<number>(-1);
const touchDragging = ref(false);

// Sort state: column key + direction
type SortCol = 'artist' | 'album' | 'year' | 'title' | 'track' | 'duration';
const sortCol = ref<SortCol>('artist');
const sortDir = ref<1 | -1>(1);
// Album sort mode: 'album' = just album name, 'artistAlbum' = artist then album
const albumSortMode = ref<'album' | 'artistAlbum'>('album');

function cycleSort(col: SortCol) {
  if (col === 'album') {
    if (sortCol.value !== 'album') {
      sortCol.value = 'album';
      sortDir.value = 1;
      albumSortMode.value = 'album';
    } else if (albumSortMode.value === 'album') {
      albumSortMode.value = 'artistAlbum';
    } else {
      sortDir.value = sortDir.value === 1 ? -1 : 1;
      albumSortMode.value = 'album';
    }
  } else {
    if (sortCol.value === col) {
      sortDir.value = sortDir.value === 1 ? -1 : 1;
    } else {
      sortCol.value = col;
      sortDir.value = 1;
    }
  }
}

function albumColLabel(): string {
  if (sortCol.value === 'album' && albumSortMode.value === 'artistAlbum') {
    return 'Album by Artist';
  }
  return 'Album';
}

function sortIndicator(col: SortCol): string {
  if (sortCol.value !== col) {
    return '';
  }
  return sortDir.value === 1 ? ' ↑' : ' ↓';
}

function sortValue(song: Song): string | number {
  switch (sortCol.value) {
    case 'artist':
      return (song.artistSort || song.artist).toLowerCase();
    case 'album':
      if (albumSortMode.value === 'artistAlbum') {
        return (
          (song.artistSort || song.artist) +
          '\0' +
          (song.albumSort || song.album)
        ).toLowerCase();
      }
      return (song.albumSort || song.album).toLowerCase();
    case 'year':
      return song.year || 0;
    case 'title':
      return song.title.toLowerCase();
    case 'track':
      return song.discNumber * 10000 + song.trackNumber;
    case 'duration':
      return song.length;
  }
}

const sortedSongs = computed<Song[]>(() => {
  const d = sortDir.value;
  return [...props.songs].sort((a, b) => {
    const av = sortValue(a);
    const bv = sortValue(b);
    if (av < bv) {
      return -d;
    }
    if (av > bv) {
      return d;
    }
    return 0;
  });
});

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function trackLabel(song: Song): string {
  if (song.trackTotal > 0) {
    return `${song.trackNumber}/${song.trackTotal}`;
  }
  return song.trackNumber > 0 ? String(song.trackNumber) : '—';
}

function isSelected(id: number): boolean {
  return selectedIds.value.has(id);
}

function selectSong(index: number, event: MouseEvent) {
  const song = sortedSongs.value[index];
  if (event.shiftKey && lastClickedIndex.value >= 0) {
    const start = Math.min(lastClickedIndex.value, index);
    const end = Math.max(lastClickedIndex.value, index);
    for (let i = start; i <= end; i++) {
      selectedIds.value.add(sortedSongs.value[i].id);
    }
  } else if (event.metaKey || event.ctrlKey) {
    if (selectedIds.value.has(song.id)) {
      selectedIds.value.delete(song.id);
    } else {
      selectedIds.value.add(song.id);
    }
    lastClickedIndex.value = index;
  } else {
    selectedIds.value = new Set([song.id]);
    lastClickedIndex.value = index;
  }
}

function selectAlbumGroup(
  albumSongs: Song[],
  index: number,
  event: MouseEvent
) {
  if (event.shiftKey || event.metaKey || event.ctrlKey) {
    for (const s of albumSongs) {
      selectedIds.value.add(s.id);
    }
  } else {
    selectedIds.value = new Set(albumSongs.map((s) => s.id));
    lastClickedIndex.value = index;
  }
}

function handleRowClick(index: number, event: MouseEvent) {
  selectSong(index, event);
}

function handleRowDblClick(index: number, event: MouseEvent) {
  selectSong(index, event);
  emit('enqueue', [...selectedIds.value]);
}

function handleAlbumGroupClick(
  albumSongs: Song[],
  index: number,
  event: MouseEvent
) {
  selectAlbumGroup(albumSongs, index, event);
}

function handleAlbumGroupDblClick(
  albumSongs: Song[],
  index: number,
  event: MouseEvent
) {
  selectAlbumGroup(albumSongs, index, event);
  emit('enqueue', [...selectedIds.value]);
}

function showContextMenu(event: MouseEvent) {
  // Let the native context menu through when Cmd/Ctrl is held.
  if (event.metaKey || event.ctrlKey) {
    return;
  }
  event.preventDefault();
  contextMenu.value = { x: event.clientX, y: event.clientY, visible: true };
}

function hideContextMenu() {
  contextMenu.value.visible = false;
}

function ctxEnqueue() {
  emit('enqueue', [...selectedIds.value]);
  hideContextMenu();
}
function ctxAppend() {
  emit('append', [...selectedIds.value]);
  hideContextMenu();
}
function ctxReplace() {
  emit('replace', [...selectedIds.value]);
  hideContextMenu();
}
function ctxMark() {
  emit('mark', [...selectedIds.value], true);
  hideContextMenu();
}
function ctxUnmark() {
  emit('mark', [...selectedIds.value], false);
  hideContextMenu();
}

// Touch drag support
function handleTouchStart(index: number, _event: TouchEvent) {
  touchStartIndex.value = index;
  touchDragging.value = false;
}

function handleTouchMove(event: TouchEvent) {
  if (touchStartIndex.value < 0) {
    return;
  }
  touchDragging.value = true;
  const touch = event.touches[0];
  const el = document.elementFromPoint(touch.clientX, touch.clientY);
  if (!el) {
    return;
  }
  const row = el.closest('[data-song-index]') as HTMLElement | null;
  if (!row) {
    return;
  }
  const idx = parseInt(row.dataset.songIndex ?? '-1', 10);
  if (idx < 0) {
    return;
  }
  const start = Math.min(touchStartIndex.value, idx);
  const end = Math.max(touchStartIndex.value, idx);
  const newSel = new Set<number>();
  for (let i = start; i <= end; i++) {
    newSel.add(sortedSongs.value[i].id);
  }
  selectedIds.value = newSel;
}

function handleTouchEnd() {
  touchStartIndex.value = -1;
}

// Album groups for grouped mode
interface AlbumGroup {
  key: string;
  artist: string;
  album: string;
  coverId: number | null;
  year: number;
  songs: Song[];
  startIndex: number;
}

const albumGroups = computed<AlbumGroup[]>(() => {
  if (!props.groupByAlbum) {
    return [];
  }
  const groups: AlbumGroup[] = [];
  const seen = new Map<string, AlbumGroup>();
  let globalIndex = 0;
  for (const song of sortedSongs.value) {
    const key = `${song.artist}|||${song.album}`;
    if (!seen.has(key)) {
      const g: AlbumGroup = {
        key,
        artist: song.artist,
        album: song.album,
        coverId: song.coverId,
        year: song.year,
        songs: [],
        startIndex: globalIndex,
      };
      seen.set(key, g);
      groups.push(g);
    }
    seen.get(key)!.songs.push(song);
    globalIndex++;
  }
  return groups;
});

// Total column count for colspan on empty row
const flatColCount = computed(() => (props.showAlbum ? 8 : 7));
</script>

<template>
  <div
    class="song-table-wrapper"
    @click.self="hideContextMenu"
    @contextmenu="showContextMenu"
  >
    <!-- Loading state -->
    <div v-if="loading" class="table-loading">Loading…</div>

    <!-- Flat (non-grouped) view -->
    <table v-else-if="!groupByAlbum" class="song-table">
      <thead>
        <tr>
          <th class="col-artist sortable" @click="cycleSort('artist')">
            Artist{{ sortIndicator('artist') }}
          </th>
          <th
            v-if="showAlbum"
            class="col-album sortable"
            @click="cycleSort('album')"
          >
            {{ albumColLabel() }}{{ sortIndicator('album') }}
          </th>
          <th class="col-year sortable" @click="cycleSort('year')">
            Year{{ sortIndicator('year') }}
          </th>
          <th class="col-title sortable" @click="cycleSort('title')">
            Title{{ sortIndicator('title') }}
          </th>
          <th class="col-track sortable" @click="cycleSort('track')">
            Track{{ sortIndicator('track') }}
          </th>
          <th class="col-duration sortable" @click="cycleSort('duration')">
            Duration{{ sortIndicator('duration') }}
          </th>
          <th class="col-mark"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(song, idx) in sortedSongs"
          :key="song.id"
          :data-song-index="idx"
          :class="{ selected: isSelected(song.id) }"
          @click="handleRowClick(idx, $event)"
          @dblclick="handleRowDblClick(idx, $event)"
          @touchstart.passive="handleTouchStart(idx, $event)"
          @touchmove.passive="handleTouchMove($event)"
          @touchend.passive="handleTouchEnd()"
        >
          <td class="col-artist">{{ song.artist }}</td>
          <td v-if="showAlbum" class="col-album">{{ song.album }}</td>
          <td class="col-year">{{ song.year || '—' }}</td>
          <td class="col-title">{{ song.title }}</td>
          <td class="col-track">{{ trackLabel(song) }}</td>
          <td class="col-duration">{{ formatDuration(song.length) }}</td>
          <td class="col-mark">{{ song.marked ? '🚩' : '' }}</td>
        </tr>
        <tr v-if="sortedSongs.length === 0">
          <td :colspan="flatColCount" class="empty-msg">No songs found.</td>
        </tr>
      </tbody>
    </table>

    <!-- Grouped-by-album view -->
    <table v-else class="song-table">
      <thead>
        <tr>
          <th class="col-cover"></th>
          <th class="col-albuminfo">Album / Artist</th>
          <th class="col-track sortable" @click="cycleSort('track')">
            Track{{ sortIndicator('track') }}
          </th>
          <th class="col-title sortable" @click="cycleSort('title')">
            Title{{ sortIndicator('title') }}
          </th>
          <th class="col-duration sortable" @click="cycleSort('duration')">
            Duration{{ sortIndicator('duration') }}
          </th>
          <th class="col-mark"></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="group in albumGroups" :key="group.key">
          <tr
            v-for="(song, si) in group.songs"
            :key="song.id"
            :data-song-index="group.startIndex + si"
            :class="{ selected: isSelected(song.id) }"
            @click="handleRowClick(group.startIndex + si, $event)"
            @dblclick="handleRowDblClick(group.startIndex + si, $event)"
          >
            <!-- Cover art and album info — only on first row of group -->
            <td
              v-if="si === 0"
              :rowspan="group.songs.length"
              class="col-cover"
              @click.stop="
                handleAlbumGroupClick(group.songs, group.startIndex, $event)
              "
              @dblclick.stop="
                handleAlbumGroupDblClick(group.songs, group.startIndex, $event)
              "
            >
              <img
                v-if="group.coverId"
                :src="`/music/cover/${group.coverId}`"
                class="album-thumb"
                loading="lazy"
              />
              <div v-else class="album-thumb-placeholder"></div>
            </td>
            <td
              v-if="si === 0"
              :rowspan="group.songs.length"
              class="col-albuminfo"
              @click.stop="
                handleAlbumGroupClick(group.songs, group.startIndex, $event)
              "
              @dblclick.stop="
                handleAlbumGroupDblClick(group.songs, group.startIndex, $event)
              "
            >
              <div class="album-name">
                {{ group.album || '(Unknown Album)' }}
              </div>
              <div class="artist-name">{{ group.artist }}</div>
              <div class="album-year">{{ group.year || '' }}</div>
            </td>
            <td class="col-track">{{ trackLabel(song) }}</td>
            <td class="col-title">{{ song.title }}</td>
            <td class="col-duration">{{ formatDuration(song.length) }}</td>
            <td class="col-mark">{{ song.marked ? '🚩' : '' }}</td>
          </tr>
        </template>
        <tr v-if="sortedSongs.length === 0">
          <td colspan="6" class="empty-msg">No songs found.</td>
        </tr>
      </tbody>
    </table>

    <!-- Context menu -->
    <div
      v-if="contextMenu.visible && selectedIds.size > 0"
      class="context-menu"
      :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
      @click.stop
    >
      <button @click="ctxEnqueue">Enqueue (after current)</button>
      <button @click="ctxAppend">Append to queue</button>
      <button @click="ctxReplace">Replace queue</button>
      <hr />
      <button @click="ctxMark">Mark</button>
      <button @click="ctxUnmark">Unmark</button>
    </div>

    <!-- Click outside to close context menu -->
    <div
      v-if="contextMenu.visible"
      class="context-overlay"
      @click="hideContextMenu"
    ></div>
  </div>
</template>

<style scoped lang="scss">
.song-table-wrapper {
  position: relative;
  width: 100%;
  overflow-x: auto;
}

.table-loading {
  color: #888;
  padding: 2rem;
  text-align: center;
}

.song-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  color: #e0e0e0;

  th {
    text-align: left;
    padding: 0.4rem 0.5rem;
    color: #999;
    font-weight: 500;
    border-bottom: 1px solid #333;
    position: sticky;
    top: 0;
    background: #1a1a1a;
    z-index: 1;
    white-space: nowrap;

    &.sortable {
      cursor: pointer;
      user-select: none;

      &:hover {
        color: #ccc;
      }
    }
  }

  td {
    padding: 0.3rem 0.5rem;
    border-bottom: 1px solid #222;
    vertical-align: middle;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
  }

  tr {
    cursor: pointer;
    &:hover {
      background: #2a2a2a;
    }
    &.selected {
      background: #1e3a5f;
      color: #90caf9;
    }
  }

  .col-artist {
    max-width: 180px;
  }
  .col-album {
    max-width: 180px;
    color: #aaa;
  }
  .col-year {
    width: 50px;
    text-align: right;
    color: #666;
  }
  .col-title {
    max-width: 240px;
  }
  .col-track {
    width: 60px;
    text-align: right;
    color: #666;
  }
  .col-duration {
    width: 60px;
    text-align: right;
    color: #777;
    font-variant-numeric: tabular-nums;
  }
  .col-mark {
    width: 24px;
    text-align: center;
    padding: 0 0.25rem;
  }
  .col-cover {
    width: 72px;
    padding: 4px;
  }
  .col-albuminfo {
    width: 160px;
    max-width: 160px;
    vertical-align: top;
    padding-top: 8px;
  }
}

.album-thumb {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 4px;
  display: block;
}

.album-thumb-placeholder {
  width: 64px;
  height: 64px;
  background: #333;
  border-radius: 4px;
}

.album-name {
  font-weight: 600;
  font-size: 0.82rem;
  color: #e0e0e0;
}
.artist-name {
  font-size: 0.78rem;
  color: #aaa;
  margin-top: 2px;
}
.album-year {
  font-size: 0.75rem;
  color: #666;
  margin-top: 2px;
}

.empty-msg {
  text-align: center;
  color: #555;
  padding: 2rem;
}

.context-menu {
  position: fixed;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.25rem 0;
  z-index: 1000;
  min-width: 160px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);

  button {
    display: block;
    width: 100%;
    background: none;
    border: none;
    color: #e0e0e0;
    padding: 0.4rem 0.75rem;
    text-align: left;
    font-size: 0.85rem;
    cursor: pointer;

    &:hover {
      background: #3b82f6;
      color: #fff;
    }
  }

  hr {
    border: none;
    border-top: 1px solid #444;
    margin: 0.25rem 0;
  }
}

.context-overlay {
  position: fixed;
  inset: 0;
  z-index: 999;
}
</style>

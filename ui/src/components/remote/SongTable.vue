<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useAdmin } from '@/composables/useAdmin';
import type { Song } from '@/types/music';

interface Props {
  songs: Song[];
  loading?: boolean;
  showAlbum?: boolean;
  showArtist?: boolean;
  showYear?: boolean;
  groupByAlbum?: boolean;
  // When true, Track column comes before Title, numbers only, default sort=track
  albumContext?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  showAlbum: true,
  showArtist: true,
  showYear: true,
  groupByAlbum: false,
  albumContext: false,
});

const emit = defineEmits<{
  enqueue: [ids: number[]];
  append: [ids: number[]];
  replace: [ids: number[]];
  mark: [ids: number[], marked: boolean];
  delete: [ids: number[]];
}>();

const { musicState } = useMusicPlayer();
const { isAdmin } = useAdmin();

// Selection state
const selectedIds = ref<Set<number>>(new Set());
const lastClickedIndex = ref<number>(-1);

// Per-row actions menu
interface RowMenu {
  songId: number;
  above: boolean;
}
const rowMenu = ref<RowMenu | null>(null);
// Ref map for action buttons: keyed by songId
const actionBtnRefs = ref<Map<number, HTMLButtonElement>>(new Map());

function setActionBtnRef(el: HTMLButtonElement | null, songId: number) {
  if (el) {
    actionBtnRefs.value.set(songId, el);
  } else {
    actionBtnRefs.value.delete(songId);
  }
}

// Floating multi-select menu
const multiMenuOpen = ref(false);

// Touch drag selection
const touchStartIndex = ref<number>(-1);

// Sort state: column key + direction
type SortCol = 'artist' | 'album' | 'year' | 'title' | 'track' | 'duration';
const sortCol = ref<SortCol>(props.albumContext ? 'track' : 'artist');
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
  // Reset scroll when sort changes
  if (scrollEl.value) {
    scrollEl.value.scrollTop = 0;
  }
  scrollTop.value = 0;
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
  if (props.albumContext) {
    return song.trackNumber > 0 ? String(song.trackNumber) : '—';
  }
  if (song.trackTotal > 0) {
    return `${song.trackNumber}/${song.trackTotal}`;
  }
  return song.trackNumber > 0 ? String(song.trackNumber) : '—';
}

function isSelected(id: number): boolean {
  return selectedIds.value.has(id);
}

function isPlaying(id: number): boolean {
  return musicState.value?.currentSongId === id;
}

// --- Selection helpers ---

function rangeSelect(fromIndex: number, toIndex: number) {
  const start = Math.min(fromIndex, toIndex);
  const end = Math.max(fromIndex, toIndex);
  for (let i = start; i <= end; i++) {
    selectedIds.value.add(sortedSongs.value[i].id);
  }
}

// Clicking the checkbox TD (or the checkbox inside it)
function handleCheckTd(index: number, event: MouseEvent) {
  event.stopPropagation();
  const song = sortedSongs.value[index];
  if (event.shiftKey && lastClickedIndex.value >= 0) {
    event.preventDefault();
    rangeSelect(lastClickedIndex.value, index);
    lastClickedIndex.value = index;
  } else {
    // Toggle
    if (selectedIds.value.has(song.id)) {
      selectedIds.value.delete(song.id);
    } else {
      selectedIds.value.add(song.id);
    }
    lastClickedIndex.value = index;
  }
}

function selectSong(index: number, event: MouseEvent) {
  const song = sortedSongs.value[index];
  if (event.shiftKey && lastClickedIndex.value >= 0) {
    event.preventDefault();
    rangeSelect(lastClickedIndex.value, index);
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

// --- Per-row actions button ---

function openRowMenu(songId: number, event: MouseEvent) {
  event.stopPropagation();

  if (rowMenu.value?.songId === songId) {
    rowMenu.value = null;
    return;
  }

  const btn = actionBtnRefs.value.get(songId);
  let above = false;
  if (btn) {
    const rect = btn.getBoundingClientRect();
    above = window.innerHeight - rect.bottom < 130;
  }
  rowMenu.value = { songId, above };
}

function closeRowMenu() {
  rowMenu.value = null;
}

function rowMenuEnqueue(songId: number) {
  emit('enqueue', [songId]);
  closeRowMenu();
}
function rowMenuAppend(songId: number) {
  emit('append', [songId]);
  closeRowMenu();
}
function rowMenuReplace(songId: number) {
  emit('replace', [songId]);
  closeRowMenu();
}
function rowMenuMark(songId: number, marked: boolean) {
  emit('mark', [songId], marked);
  closeRowMenu();
}
function rowMenuDelete(songId: number) {
  emit('delete', [songId]);
  closeRowMenu();
}

// --- Multi-select floating bar ---

const selectedCount = computed(() => selectedIds.value.size);
const multiIds = computed(() => [...selectedIds.value]);

function multiEnqueue() {
  emit('enqueue', multiIds.value);
  multiMenuOpen.value = false;
}
function multiAppend() {
  emit('append', multiIds.value);
  multiMenuOpen.value = false;
}
function multiReplace() {
  emit('replace', multiIds.value);
  multiMenuOpen.value = false;
}
function multiMark(marked: boolean) {
  emit('mark', multiIds.value, marked);
  multiMenuOpen.value = false;
}
function multiDelete() {
  emit('delete', multiIds.value);
  multiMenuOpen.value = false;
  selectedIds.value = new Set();
}
function clearSelection() {
  selectedIds.value = new Set();
  multiMenuOpen.value = false;
}

// Touch drag support
function handleTouchStart(index: number, _event: TouchEvent) {
  touchStartIndex.value = index;
}

function handleTouchMove(event: TouchEvent) {
  if (touchStartIndex.value < 0) {
    return;
  }
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

// ─── Virtual scrolling (flat view only) ──────────────────────────────────────

const ROW_H = 29; // px — must match .vrow height in CSS
const OVERSCAN = 5;

const scrollEl = ref<HTMLElement | null>(null);
const scrollTop = ref(0);
const viewportH = ref(400);

function onScroll() {
  if (scrollEl.value) {
    scrollTop.value = scrollEl.value.scrollTop;
  }
}

let ro: ResizeObserver | null = null;

onMounted(() => {
  if (scrollEl.value) {
    ro = new ResizeObserver((entries) => {
      viewportH.value = entries[0].contentRect.height;
    });
    ro.observe(scrollEl.value);
    viewportH.value = scrollEl.value.clientHeight;
  }
});

onUnmounted(() => {
  ro?.disconnect();
});

// Reset scroll position when songs list changes (e.g. new search results)
watch(
  () => props.songs,
  () => {
    if (scrollEl.value) {
      scrollEl.value.scrollTop = 0;
    }
    scrollTop.value = 0;
  }
);

const visibleRange = computed(() => {
  const total = sortedSongs.value.length;
  const first = Math.max(0, Math.floor(scrollTop.value / ROW_H) - OVERSCAN);
  const visibleCount = Math.ceil(viewportH.value / ROW_H) + OVERSCAN * 2;
  const last = Math.min(total - 1, first + visibleCount);
  return { first, last };
});

const visibleSongs = computed(() =>
  sortedSongs.value.slice(visibleRange.value.first, visibleRange.value.last + 1)
);

const spacerTop = computed(() => visibleRange.value.first * ROW_H);
const spacerBottom = computed(
  () => (sortedSongs.value.length - 1 - visibleRange.value.last) * ROW_H
);

// ─── Select-all ──────────────────────────────────────────────────────────────

// 0 = none, 1 = some, 2 = all
const selectionState = computed<0 | 1 | 2>(() => {
  const count = selectedIds.value.size;
  if (count === 0) {
    return 0;
  }
  if (count >= sortedSongs.value.length) {
    return 2;
  }
  return 1;
});

function toggleSelectAll() {
  if (selectionState.value === 0) {
    selectedIds.value = new Set(sortedSongs.value.map((s) => s.id));
  } else {
    selectedIds.value = new Set();
  }
}

// ─── Drag support ────────────────────────────────────────────────────────────

function onRowDragStart(songId: number, e: DragEvent) {
  if (!e.dataTransfer) {
    return;
  }
  // Include the dragged song plus any other selected songs
  const ids = selectedIds.value.has(songId) ? [...selectedIds.value] : [songId];
  e.dataTransfer.effectAllowed = 'copy';
  e.dataTransfer.setData('application/x-song-ids', JSON.stringify(ids));
}

// Grid template columns for the flat virtual list
const gridCols = computed(() => {
  const cols: string[] = [];
  cols.push('28px'); // checkbox
  if (props.showArtist) {
    cols.push('minmax(80px, 1.5fr)');
  }
  if (props.showAlbum) {
    cols.push('minmax(80px, 1.5fr)');
  }
  if (props.albumContext) {
    cols.push('44px'); // track before title
  }
  cols.push('minmax(100px, 2fr)'); // title
  if (!props.albumContext) {
    cols.push('52px'); // track after title
  }
  cols.push('56px'); // duration
  if (props.showYear) {
    cols.push('48px');
  }
  cols.push('36px'); // actions
  return cols.join(' ');
});
</script>

<template>
  <div class="song-table-wrapper">
    <!-- Loading state -->
    <div v-if="loading" class="table-loading">Loading…</div>

    <!-- Flat virtual-scroll view -->
    <template v-else-if="!groupByAlbum">
      <!-- Sticky header -->
      <div class="vlist-header" :style="{ gridTemplateColumns: gridCols }">
        <div class="vh-check" @click="toggleSelectAll">
          <input
            type="checkbox"
            :checked="selectionState === 2"
            :indeterminate="selectionState === 1"
            tabindex="-1"
            @click.stop
          />
        </div>
        <div
          v-if="showArtist"
          class="vh-cell sortable"
          @click="cycleSort('artist')"
        >
          Artist{{ sortIndicator('artist') }}
        </div>
        <div
          v-if="showAlbum"
          class="vh-cell sortable"
          @click="cycleSort('album')"
        >
          {{ albumColLabel() }}{{ sortIndicator('album') }}
        </div>
        <div
          v-if="albumContext"
          class="vh-cell vh-num sortable"
          @click="cycleSort('track')"
        >
          #{{ sortIndicator('track') }}
        </div>
        <div class="vh-cell sortable" @click="cycleSort('title')">
          Title{{ sortIndicator('title') }}
        </div>
        <div
          v-if="!albumContext"
          class="vh-cell vh-num sortable"
          @click="cycleSort('track')"
        >
          Track{{ sortIndicator('track') }}
        </div>
        <div class="vh-cell vh-num sortable" @click="cycleSort('duration')">
          Duration{{ sortIndicator('duration') }}
        </div>
        <div
          v-if="showYear"
          class="vh-cell vh-num sortable"
          @click="cycleSort('year')"
        >
          Year{{ sortIndicator('year') }}
        </div>
        <div class="vh-check"></div>
      </div>

      <!-- Scroll body -->
      <div ref="scrollEl" class="vscroll" @scroll.passive="onScroll">
        <!-- top spacer -->
        <div :style="{ height: spacerTop + 'px' }"></div>

        <div
          v-for="(song, vi) in visibleSongs"
          :key="song.id"
          class="vrow"
          :data-song-index="visibleRange.first + vi"
          :class="{
            selected: isSelected(song.id),
            playing: isPlaying(song.id),
          }"
          :style="{ gridTemplateColumns: gridCols }"
          draggable="true"
          @click="handleRowClick(visibleRange.first + vi, $event)"
          @dblclick="handleRowDblClick(visibleRange.first + vi, $event)"
          @dragstart="onRowDragStart(song.id, $event)"
          @touchstart.passive="
            handleTouchStart(visibleRange.first + vi, $event)
          "
          @touchmove.passive="handleTouchMove($event)"
          @touchend.passive="handleTouchEnd()"
        >
          <div
            class="vc-check"
            @click.stop="handleCheckTd(visibleRange.first + vi, $event)"
          >
            <input
              type="checkbox"
              :checked="isSelected(song.id)"
              tabindex="-1"
              @click.stop
            />
          </div>
          <div v-if="showArtist" class="vc-cell vc-artist">
            {{ song.artist }}
          </div>
          <div v-if="showAlbum" class="vc-cell vc-album">{{ song.album }}</div>
          <div v-if="albumContext" class="vc-cell vc-num">
            {{ trackLabel(song) }}
          </div>
          <div
            class="vc-cell vc-title"
            :class="{ 'now-playing': isPlaying(song.id) }"
          >
            {{ song.title
            }}<span v-if="song.marked" class="flag-icon" title="Marked"
              >🚩</span
            >
          </div>
          <div v-if="!albumContext" class="vc-cell vc-num">
            {{ trackLabel(song) }}
          </div>
          <div class="vc-cell vc-num vc-duration">
            {{ formatDuration(song.length) }}
          </div>
          <div v-if="showYear" class="vc-cell vc-num vc-year">
            {{ song.year || '—' }}
          </div>
          <!-- Per-row actions -->
          <div class="vc-actions" @click.stop>
            <div class="row-action-wrap">
              <button
                :ref="
                  (el) =>
                    setActionBtnRef(el as HTMLButtonElement | null, song.id)
                "
                class="row-action-btn"
                title="Actions"
                @click="openRowMenu(song.id, $event)"
              >
                …
              </button>
              <div
                v-if="rowMenu?.songId === song.id"
                class="row-menu"
                :class="{ above: rowMenu.above }"
                @click.stop
              >
                <button @click="rowMenuEnqueue(song.id)">Play next</button>
                <button @click="rowMenuAppend(song.id)">Add to end</button>
                <button @click="rowMenuReplace(song.id)">Replace queue</button>
                <hr />
                <button @click="rowMenuMark(song.id, !song.marked)">
                  {{ song.marked ? 'Unmark' : 'Mark' }}
                </button>
                <template v-if="isAdmin">
                  <hr />
                  <button class="menu-danger" @click="rowMenuDelete(song.id)">
                    Delete
                  </button>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- bottom spacer -->
        <div :style="{ height: spacerBottom + 'px' }"></div>

        <div v-if="sortedSongs.length === 0" class="empty-msg">
          No songs found.
        </div>
      </div>
    </template>

    <!-- Grouped-by-album view (normal table, no virtualization) -->
    <div v-else class="grouped-scroll">
      <table class="song-table">
        <thead>
          <tr>
            <th class="col-check"></th>
            <th class="col-cover"></th>
            <th class="col-albuminfo">Album / Artist</th>
            <th class="col-track sortable" @click="cycleSort('track')">
              #{{ sortIndicator('track') }}
            </th>
            <th class="col-title sortable" @click="cycleSort('title')">
              Title{{ sortIndicator('title') }}
            </th>
            <th class="col-duration sortable" @click="cycleSort('duration')">
              Duration{{ sortIndicator('duration') }}
            </th>
            <th class="col-actions"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="group in albumGroups" :key="group.key">
            <tr
              v-for="(song, si) in group.songs"
              :key="song.id"
              :data-song-index="group.startIndex + si"
              :class="{
                selected: isSelected(song.id),
                playing: isPlaying(song.id),
              }"
              draggable="true"
              @click="handleRowClick(group.startIndex + si, $event)"
              @dblclick="handleRowDblClick(group.startIndex + si, $event)"
              @dragstart="onRowDragStart(song.id, $event)"
            >
              <td
                class="col-check"
                @click.stop="handleCheckTd(group.startIndex + si, $event)"
              >
                <input
                  type="checkbox"
                  :checked="isSelected(song.id)"
                  tabindex="-1"
                  @click.stop
                />
              </td>
              <!-- Cover art and album info — only on first row of group -->
              <td
                v-if="si === 0"
                :rowspan="group.songs.length"
                class="col-cover"
                @click.stop="
                  handleAlbumGroupClick(group.songs, group.startIndex, $event)
                "
                @dblclick.stop="
                  handleAlbumGroupDblClick(
                    group.songs,
                    group.startIndex,
                    $event
                  )
                "
              >
                <img
                  v-if="group.coverId"
                  :src="`/music/cover/${group.coverId}`"
                  class="album-thumb"
                  loading="lazy"
                />
                <img
                  v-else
                  src="/img/no-cover.svg"
                  class="album-thumb"
                  alt=""
                />
              </td>
              <td
                v-if="si === 0"
                :rowspan="group.songs.length"
                class="col-albuminfo"
                @click.stop="
                  handleAlbumGroupClick(group.songs, group.startIndex, $event)
                "
                @dblclick.stop="
                  handleAlbumGroupDblClick(
                    group.songs,
                    group.startIndex,
                    $event
                  )
                "
              >
                <div class="album-name">
                  {{ group.album || '(Unknown Album)' }}
                </div>
                <div class="artist-name">{{ group.artist }}</div>
                <div class="album-year">{{ group.year || '' }}</div>
              </td>
              <td class="col-track">{{ trackLabel(song) }}</td>
              <td
                class="col-title"
                :class="{ 'now-playing': isPlaying(song.id) }"
              >
                {{ song.title
                }}<span v-if="song.marked" class="flag-icon" title="Marked"
                  >🚩</span
                >
              </td>
              <td class="col-duration">{{ formatDuration(song.length) }}</td>
              <!-- Per-row actions -->
              <td class="col-actions" @click.stop>
                <div class="row-action-wrap">
                  <button
                    :ref="
                      (el) =>
                        setActionBtnRef(el as HTMLButtonElement | null, song.id)
                    "
                    class="row-action-btn"
                    title="Actions"
                    @click="openRowMenu(song.id, $event)"
                  >
                    …
                  </button>
                  <div
                    v-if="rowMenu?.songId === song.id"
                    class="row-menu"
                    :class="{ above: rowMenu.above }"
                    @click.stop
                  >
                    <button @click="rowMenuEnqueue(song.id)">Play next</button>
                    <button @click="rowMenuAppend(song.id)">Add to end</button>
                    <button @click="rowMenuReplace(song.id)">
                      Replace queue
                    </button>
                    <hr />
                    <button @click="rowMenuMark(song.id, !song.marked)">
                      {{ song.marked ? 'Unmark' : 'Mark' }}
                    </button>
                    <template v-if="isAdmin">
                      <hr />
                      <button
                        class="menu-danger"
                        @click="rowMenuDelete(song.id)"
                      >
                        Delete
                      </button>
                    </template>
                  </div>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="sortedSongs.length === 0">
            <td colspan="7" class="empty-msg">No songs found.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Click-outside overlay for row menu -->
    <div v-if="rowMenu" class="menu-overlay" @click="closeRowMenu" />

    <!-- Floating multi-select bar -->
    <Teleport to="body">
      <Transition name="float-bar">
        <div v-if="selectedCount > 1" class="multi-select-bar">
          <span class="multi-count">{{ selectedCount }} songs selected</span>
          <div class="multi-actions">
            <button @click="multiEnqueue">Play next</button>
            <button @click="multiAppend">Add to end</button>
            <button @click="multiReplace">Replace</button>
            <button
              class="multi-menu-btn"
              @click="multiMenuOpen = !multiMenuOpen"
            >
              More ▾
            </button>
            <div v-if="multiMenuOpen" class="multi-menu" @click.stop>
              <button @click="multiMark(true)">Mark all</button>
              <button @click="multiMark(false)">Unmark all</button>
              <template v-if="isAdmin">
                <hr />
                <button class="menu-danger" @click="multiDelete">
                  Delete all
                </button>
              </template>
            </div>
          </div>
          <button
            class="multi-close"
            title="Clear selection"
            @click="clearSelection"
          >
            ✕
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.song-table-wrapper {
  position: relative;
  width: 100%;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  user-select: none;
}

.table-loading {
  color: #888;
  padding: 2rem;
  text-align: center;
}

// ─── Virtual flat list ────────────────────────────────────────────────────────

.vlist-header {
  display: grid;
  flex-shrink: 0;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  font-size: 0.85rem;
  color: #999;
  font-weight: 500;
  white-space: nowrap;
}

.vh-check {
  width: 28px;
  padding: 0.4rem 0.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;

  input[type='checkbox'] {
    cursor: pointer;
    accent-color: #3b82f6;
    pointer-events: none;
  }
}

.vh-cell {
  padding: 0.4rem 0.5rem;

  &.sortable {
    cursor: pointer;

    &:hover {
      color: #ccc;
    }
  }

  &.vh-num {
    text-align: right;
  }
}

.vscroll {
  flex: 1;
  overflow-y: scroll;
  min-height: 0;
}

.vrow {
  display: grid;
  height: 29px; // must match ROW_H constant
  align-items: center;
  cursor: pointer;
  border-bottom: 1px solid #222;
  font-size: 0.85rem;
  color: #e0e0e0;

  &:hover {
    background: #2a2a2a;

    .row-action-btn {
      opacity: 1;
      color: #888;
    }
  }

  &.selected {
    background: #1e3a5f;
    color: #90caf9;
  }

  &.playing {
    background: #1a2e1a;
  }

  &.selected.playing {
    background: #1a3a2a;
  }
}

.vc-check {
  width: 28px;
  padding: 0 0.25rem;
  text-align: center;
  cursor: default;
  display: flex;
  align-items: center;
  justify-content: center;

  input[type='checkbox'] {
    cursor: pointer;
    accent-color: #3b82f6;
    pointer-events: none;
  }
}

.vc-cell {
  padding: 0 0.5rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  &.vc-artist {
    color: #e0e0e0;
  }

  &.vc-album {
    color: #aaa;
  }

  &.vc-num {
    text-align: right;
    color: #666;
    font-variant-numeric: tabular-nums;
  }

  &.vc-duration {
    color: #777;
  }

  &.vc-year {
    color: #666;
  }

  &.vc-title {
    color: #e0e0e0;

    &.now-playing {
      font-weight: 700;
      color: #4ade80;
    }
  }
}

.vc-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: visible;
}

.grouped-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

// ─── Grouped table (unchanged) ───────────────────────────────────────────────

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
    &.playing {
      background: #1a2e1a;
    }
    &.selected.playing {
      background: #1a3a2a;
    }
  }

  .col-check {
    width: 28px;
    padding: 0 0.25rem;
    text-align: center;
    cursor: default;

    input[type='checkbox'] {
      cursor: pointer;
      accent-color: #3b82f6;
      pointer-events: none; // td handles the click
    }
  }
  .col-album {
    max-width: 180px;
    color: #aaa;
  }
  .col-title {
    max-width: 240px;

    &.now-playing {
      font-weight: 700;
      color: #4ade80;
    }
  }
  .col-track {
    width: 48px;
    text-align: right;
    color: #666;
  }
  .col-duration {
    width: 60px;
    text-align: right;
    color: #777;
    font-variant-numeric: tabular-nums;
  }
  .col-actions {
    width: 32px;
    padding: 0 0.2rem;
    text-align: center;
    overflow: visible;
  }
  .col-cover {
    width: 88px;
    padding: 4px;
    vertical-align: top;
  }
  .col-albuminfo {
    width: 160px;
    max-width: 160px;
    vertical-align: top;
    padding-top: 8px;
  }
}

.flag-icon {
  margin-left: 4px;
  font-size: 0.75em;
}

.album-thumb {
  width: 80px;
  height: auto;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
  display: block;
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
  font-size: 0.85rem;
}

// ─── Per-row actions ──────────────────────────────────────────────────────────

.row-action-wrap {
  position: relative;
  display: inline-block;
}

.row-action-btn {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 1rem;
  line-height: 1;
  opacity: 0;

  tr:hover &,
  .vrow:hover & {
    opacity: 1;
    color: #888;
  }

  &:hover {
    background: #333;
    color: #ccc !important;
  }
}

.row-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 2px);
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.25rem 0;
  z-index: 500;
  min-width: 150px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
  white-space: nowrap;

  &.above {
    top: auto;
    bottom: calc(100% + 2px);
  }

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

    &.menu-danger {
      color: #f87171;

      &:hover {
        background: #7f1d1d;
        color: #fca5a5;
      }
    }
  }

  hr {
    border: none;
    border-top: 1px solid #444;
    margin: 0.25rem 0;
  }
}

.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 499;
}

// ─── Floating multi-select bar ────────────────────────────────────────────────

.multi-select-bar {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  background: #1e3a5f;
  border: 1px solid #2a5a9f;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.7);
  z-index: 300;
  white-space: nowrap;
  color: #90caf9;
  font-size: 0.85rem;
}

.multi-count {
  font-weight: 600;
  margin-right: 0.25rem;
}

.multi-actions {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  position: relative;

  button {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    color: #90caf9;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;

    &:hover {
      background: rgba(255, 255, 255, 0.2);
      color: #fff;
    }
  }
}

.multi-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.25rem 0;
  z-index: 310;
  min-width: 140px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);

  button {
    display: block;
    width: 100%;
    background: none !important;
    border: none !important;
    color: #e0e0e0 !important;
    padding: 0.4rem 0.75rem;
    text-align: left;
    font-size: 0.85rem;
    cursor: pointer;
    border-radius: 0 !important;

    &:hover {
      background: #3b82f6 !important;
      color: #fff !important;
    }

    &.menu-danger {
      color: #f87171 !important;

      &:hover {
        background: #7f1d1d !important;
        color: #fca5a5 !important;
      }
    }
  }

  hr {
    border: none;
    border-top: 1px solid #444;
    margin: 0.25rem 0;
  }
}

.multi-close {
  background: none;
  border: none;
  color: #90caf9;
  cursor: pointer;
  padding: 0.2rem 0.3rem;
  font-size: 0.8rem;
  border-radius: 3px;
  margin-left: 0.25rem;

  &:hover {
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
  }
}

.float-bar-enter-active,
.float-bar-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}
.float-bar-enter-from,
.float-bar-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>

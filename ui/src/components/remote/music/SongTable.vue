<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongSort } from '@/composables/useSongSort';
import { useSongSelection } from '@/composables/useSongSelection';
import {
  useSongActions,
  type SongTableEmit,
} from '@/composables/useSongActions';
import { useVirtualScroll } from '@/composables/useVirtualScroll';
import SongFlagButtons from '@/components/remote/music/SongFlagButtons.vue';
import SongRowMenu from '@/components/remote/music/SongRowMenu.vue';
import SongMultiBar from '@/components/remote/music/SongMultiBar.vue';
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
  // When true: preserves song order, enables drag-reorder, adds Remove action
  playlistMode?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  showAlbum: true,
  showArtist: true,
  showYear: true,
  groupByAlbum: false,
  albumContext: false,
  playlistMode: false,
});

const emit = defineEmits<{
  enqueue: [ids: number[]];
  append: [ids: number[]];
  replace: [ids: number[]];
  mark: [ids: number[], marked: boolean];
  favorite: [ids: number[], favorite: boolean];
  delete: [ids: number[]];
  edit: [ids: number[]];
  'remove-from-playlist': [ids: number[]];
  reorder: [fromIndex: number, toIndex: number];
}>();

const { musicState } = useMusicPlayer();

// Shared scroll state — created here so both useSongSort and useVirtualScroll
// can reset it without circular dependencies.
const scrollEl = ref<HTMLElement | null>(null);
const scrollTop = ref(0);

const {
  sortCol,
  sortDir,
  sortedSongs,
  resolvedSongs,
  albumGroups,
  cycleSort,
  sortIndicator,
  albumColLabel,
  formatDuration,
  trackLabel,
  onMobileSortChange,
  toggleSortDir,
} = useSongSort(
  () => props.songs,
  () => props.albumContext,
  () => props.groupByAlbum,
  () => props.playlistMode,
  scrollEl,
  scrollTop
);

const {
  selectedIds,
  selectionState,
  selectedCount,
  multiIds,
  isSelected,
  clearSelection,
  toggleSelectAll,
  handleCheckTd,
  handleCheckTdTouchStart,
  handleCheckTdTouchEnd,
  cancelLongPress,
  handleRowClick,
  handleAlbumGroupClick,
} = useSongSelection(
  () => sortedSongs.value,
  () => props.playlistMode
);

// Thin adapter so useSongActions has no dependency on Vue's defineEmits
const emitAdapter: SongTableEmit = {
  enqueue: (ids) => emit('enqueue', ids),
  append: (ids) => emit('append', ids),
  replace: (ids) => emit('replace', ids),
  mark: (ids, marked) => emit('mark', ids, marked),
  favorite: (ids, fav) => emit('favorite', ids, fav),
  delete: (ids) => emit('delete', ids),
  edit: (ids) => emit('edit', ids),
  removeFromPlaylist: (ids) => emit('remove-from-playlist', ids),
};

const {
  isAdmin,
  rowMenu,
  openRowMenu,
  closeRowMenu,
  handleFlagChange,
  rowMenuEnqueue,
  rowMenuAppend,
  rowMenuReplace,
  rowMenuMark,
  rowMenuFavorite,
  rowMenuEdit,
  rowMenuDelete,
  rowMenuRemoveFromPlaylist,
  multiEnqueue,
  multiAppend,
  multiReplace,
  multiMark,
  multiFavorite,
  multiEdit,
  multiDelete,
  multiRemoveFromPlaylist,
} = useSongActions(emitAdapter, () => props.songs, multiIds, clearSelection);

const {
  isMobile,
  visibleRange,
  visibleSongs,
  spacerTop,
  spacerBottom,
  gridCols,
  onScroll,
} = useVirtualScroll(
  () => sortedSongs.value,
  () => resolvedSongs.value,
  () => props.songs,
  () => props.showArtist,
  () => props.showAlbum,
  () => props.showYear,
  () => props.albumContext,
  () => props.playlistMode,
  scrollEl,
  scrollTop
);

function isPlaying(id: number): boolean {
  return musicState.value?.currentSongId === id;
}

// Double-click: select + enqueue
function handleRowDblClick(index: number, event: MouseEvent) {
  handleRowClick(index, event);
  emit('enqueue', [...selectedIds.value]);
}

function handleAlbumGroupDblClick(
  albumSongs: Song[],
  index: number,
  event: MouseEvent
) {
  handleAlbumGroupClick(albumSongs, index, event);
  emit('enqueue', [...selectedIds.value]);
}

// Delete key — removes from playlist when in playlistMode
function handleKeyDown(e: KeyboardEvent) {
  if (!props.playlistMode) {
    return;
  }
  if (e.key !== 'Delete' && e.key !== 'Backspace') {
    return;
  }
  if (selectedIds.value.size === 0) {
    return;
  }
  emit('remove-from-playlist', [...selectedIds.value]);
  clearSelection();
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

// ─── Drag support ─────────────────────────────────────────────────────────────

function onRowDragStart(songId: number, index: number, e: DragEvent) {
  if (!e.dataTransfer) {
    return;
  }
  if (props.playlistMode) {
    // In playlist mode, drag carries the playlist index for reordering
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('application/x-playlist-index', String(index));
    plDragFromIndex.value = index;
  } else {
    // Include the dragged song plus any other selected songs
    const ids = selectedIds.value.has(songId)
      ? [...selectedIds.value]
      : [songId];
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData('application/x-song-ids', JSON.stringify(ids));
  }
}

// ─── Playlist drag-reorder ────────────────────────────────────────────────────

const plDragFromIndex = ref<number | null>(null);
const plDropIndicator = ref<{
  index: number;
  position: 'above' | 'below';
} | null>(null);

function onPlDragOver(index: number, e: DragEvent) {
  if (!props.playlistMode) {
    return;
  }
  if (!e.dataTransfer?.types.includes('application/x-playlist-index')) {
    return;
  }
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  const target = e.currentTarget as HTMLElement;
  const rect = target.getBoundingClientRect();
  const position: 'above' | 'below' =
    e.clientY < rect.top + rect.height / 2 ? 'above' : 'below';
  plDropIndicator.value = { index, position };
}

function onPlDragEnd() {
  plDragFromIndex.value = null;
  plDropIndicator.value = null;
}

function onPlDrop(index: number, e: DragEvent) {
  e.preventDefault();
  const from = plDragFromIndex.value;
  plDragFromIndex.value = null;
  const indicator = plDropIndicator.value;
  plDropIndicator.value = null;
  if (from === null || !indicator) {
    return;
  }
  let to = indicator.position === 'above' ? index : index + 1;
  if (from < to) {
    to--;
  }
  if (from !== to) {
    emit('reorder', from, to);
  }
}
</script>

<template>
  <div class="song-table-wrapper">
    <!-- Loading state -->
    <div v-if="loading" class="table-loading">Loading…</div>

    <!-- Flat virtual-scroll view -->
    <template v-else-if="!groupByAlbum">
      <!-- Sticky header -->
      <div class="vlist-header" :style="{ gridTemplateColumns: gridCols }">
        <div v-if="playlistMode" class="vh-drag-col"></div>
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
          class="vh-cell"
          :class="{ sortable: !playlistMode }"
          @click="!playlistMode && cycleSort('artist')"
        >
          Artist{{ !playlistMode ? sortIndicator('artist') : '' }}
        </div>
        <div
          v-if="showAlbum"
          class="vh-cell"
          :class="{ sortable: !playlistMode }"
          @click="!playlistMode && cycleSort('album')"
        >
          {{ albumColLabel() }}{{ !playlistMode ? sortIndicator('album') : '' }}
        </div>
        <div
          v-if="albumContext"
          class="vh-cell vh-num"
          :class="{ sortable: !playlistMode }"
          @click="!playlistMode && cycleSort('track')"
        >
          #{{ !playlistMode ? sortIndicator('track') : '' }}
        </div>
        <div
          class="vh-cell"
          :class="{ sortable: !playlistMode }"
          @click="!playlistMode && cycleSort('title')"
        >
          Title{{ !playlistMode ? sortIndicator('title') : '' }}
        </div>
        <div
          v-if="!albumContext"
          class="vh-cell vh-num"
          :class="{ sortable: !playlistMode }"
          @click="!playlistMode && cycleSort('track')"
        >
          Track{{ !playlistMode ? sortIndicator('track') : '' }}
        </div>
        <div
          class="vh-cell vh-num"
          :class="{ sortable: !playlistMode }"
          @click="!playlistMode && cycleSort('duration')"
        >
          Duration{{ !playlistMode ? sortIndicator('duration') : '' }}
        </div>
        <div
          v-if="showYear"
          class="vh-cell vh-num"
          :class="{ sortable: !playlistMode }"
          @click="!playlistMode && cycleSort('year')"
        >
          Year{{ !playlistMode ? sortIndicator('year') : '' }}
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
            'pl-drop-above':
              plDropIndicator?.index === visibleRange.first + vi &&
              plDropIndicator.position === 'above',
            'pl-drop-below':
              plDropIndicator?.index === visibleRange.first + vi &&
              plDropIndicator.position === 'below',
          }"
          :style="{ gridTemplateColumns: gridCols }"
          draggable="true"
          @click="handleRowClick(visibleRange.first + vi, $event)"
          @dblclick="handleRowDblClick(visibleRange.first + vi, $event)"
          @dragstart="onRowDragStart(song.id, visibleRange.first + vi, $event)"
          @dragover="onPlDragOver(visibleRange.first + vi, $event)"
          @dragend="onPlDragEnd"
          @drop="onPlDrop(visibleRange.first + vi, $event)"
        >
          <!-- Mobile compact cover art (hidden on desktop) -->
          <div class="vc-cover">
            <img
              v-if="song.coverId"
              :src="`/music/cover/${song.coverId}`"
              class="vc-thumb"
              loading="lazy"
              alt=""
            />
            <img v-else src="/img/no-cover.svg" class="vc-thumb" alt="" />
          </div>
          <div v-if="playlistMode" class="vc-drag-handle" @click.stop>⠿</div>
          <div
            class="vc-check"
            @click.stop="handleCheckTd(visibleRange.first + vi, $event)"
            @touchstart.stop="handleCheckTdTouchStart(visibleRange.first + vi)"
            @touchend.stop="handleCheckTdTouchEnd($event)"
            @touchmove.passive="cancelLongPress"
            @touchcancel="cancelLongPress"
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
            <span class="title-text">{{ song.title }}</span>
            <SongFlagButtons
              v-if="!isMobile"
              :song="song"
              variant="row"
              @change="(field, val) => handleFlagChange(song.id, field, val)"
            />
            <!-- Mobile subtitle: artist — album -->
            <div class="vc-mobile-sub">
              <span>{{ song.artist }}</span>
              <template v-if="song.album">
                <span class="vc-sub-sep"> — </span>
                <span>{{ song.album }}</span>
              </template>
            </div>
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
            <SongRowMenu
              :song="song"
              :is-open="rowMenu?.songId === song.id"
              :is-admin="isAdmin"
              :playlist-mode="playlistMode"
              @open="openRowMenu(song.id, $event)"
              @enqueue="rowMenuEnqueue(song.id)"
              @append="rowMenuAppend(song.id)"
              @replace="rowMenuReplace(song.id)"
              @mark="(v) => rowMenuMark(song.id, v)"
              @favorite="(v) => rowMenuFavorite(song.id, v)"
              @edit="rowMenuEdit(song.id)"
              @delete="rowMenuDelete(song.id)"
              @remove-from-playlist="rowMenuRemoveFromPlaylist(song.id)"
            />
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
            <th class="col-cover">Album / Artist</th>
            <th class="col-check"></th>
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
              @dragstart="
                onRowDragStart(song.id, group.startIndex + si, $event)
              "
            >
              <!-- Cover art and album info merged — only on first row of group -->
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
                <div class="album-name">
                  {{ group.album || '(Unknown Album)' }}
                </div>
                <div class="artist-name">{{ group.artist }}</div>
                <div class="album-year">{{ group.year || '' }}</div>
              </td>
              <td
                class="col-check"
                @click.stop="handleCheckTd(group.startIndex + si, $event)"
                @touchstart.stop="
                  handleCheckTdTouchStart(group.startIndex + si)
                "
                @touchend.stop="handleCheckTdTouchEnd($event)"
                @touchmove.passive="cancelLongPress"
                @touchcancel="cancelLongPress"
              >
                <input
                  type="checkbox"
                  :checked="isSelected(song.id)"
                  tabindex="-1"
                  @click.stop
                />
              </td>
              <td class="col-track">{{ trackLabel(song) }}</td>
              <td
                class="col-title"
                :class="{ 'now-playing': isPlaying(song.id) }"
              >
                <div class="col-title-inner">
                  <span class="title-text">{{ song.title }}</span>
                  <SongFlagButtons
                    :song="song"
                    variant="row"
                    @change="
                      (field, val) => handleFlagChange(song.id, field, val)
                    "
                  />
                </div>
              </td>
              <td class="col-duration">{{ formatDuration(song.length) }}</td>
              <!-- Per-row actions (no Favorite, no playlist mode in grouped view) -->
              <td class="col-actions" @click.stop>
                <SongRowMenu
                  :song="song"
                  :is-open="rowMenu?.songId === song.id"
                  :is-admin="isAdmin"
                  :playlist-mode="false"
                  :show-favorite="false"
                  @open="openRowMenu(song.id, $event)"
                  @enqueue="rowMenuEnqueue(song.id)"
                  @append="rowMenuAppend(song.id)"
                  @replace="rowMenuReplace(song.id)"
                  @mark="(v) => rowMenuMark(song.id, v)"
                  @edit="rowMenuEdit(song.id)"
                  @delete="rowMenuDelete(song.id)"
                />
              </td>
            </tr>
          </template>
          <tr v-if="sortedSongs.length === 0">
            <td colspan="6" class="empty-msg">No songs found.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Teleport sort controls into music.vue header row on mobile -->
    <Teleport
      v-if="isMobile && !playlistMode && !groupByAlbum"
      to="#mobile-sort-portal"
    >
      <div class="mobile-sort-inline">
        <select
          :value="sortCol"
          class="mobile-sort-select"
          @change="onMobileSortChange"
        >
          <option v-if="showArtist" value="artist">Artist</option>
          <option v-if="showAlbum" value="album">Album</option>
          <option value="title">Title</option>
          <option value="track">Track</option>
          <option value="duration">Dur.</option>
          <option v-if="showYear" value="year">Year</option>
        </select>
        <button class="mobile-sort-dir" @click="toggleSortDir">
          {{ sortDir === 1 ? '↑' : '↓' }}
        </button>
      </div>
    </Teleport>

    <!-- Click-outside overlay for row menu -->
    <div v-if="rowMenu" class="menu-overlay" @click="closeRowMenu" />

    <!-- Floating multi-select bar (self-contained with Teleport) -->
    <SongMultiBar
      :count="selectedCount"
      :is-admin="isAdmin"
      :playlist-mode="playlistMode"
      @enqueue="multiEnqueue"
      @append="multiAppend"
      @replace="multiReplace"
      @mark="multiMark"
      @favorite="multiFavorite"
      @edit="multiEdit"
      @delete="multiDelete"
      @remove-from-playlist="multiRemoveFromPlaylist"
      @clear="clearSelection"
    />
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
  -webkit-user-select: none;
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
  // Reserve same scrollbar gutter as .vscroll so columns align
  overflow-y: scroll;
  overflow-x: hidden;

  // Hide the scrollbar track itself
  &::-webkit-scrollbar {
    background: #1a1a1a;
  }
  &::-webkit-scrollbar-thumb {
    background: transparent;
  }
  scrollbar-color: transparent #1a1a1a;
}

.vh-drag-col {
  width: 20px;
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

    @media (hover: hover) {
      &:hover {
        color: #ccc;
      }
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

  @media (hover: hover) {
    &:hover {
      background: #2a2a2a;

      // Reveal the "..." button on row hover (button is in SongRowMenu child)
      :deep(.row-action-btn) {
        opacity: 1;
        color: #888;
      }
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

.vc-drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  cursor: grab;
  font-size: 0.9rem;
  user-select: none;

  &:active {
    cursor: grabbing;
  }
}

.vrow.pl-drop-above {
  border-top: 2px solid #3b82f6;
}

.vrow.pl-drop-below {
  border-bottom: 2px solid #3b82f6;
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

// ─── Grouped table ────────────────────────────────────────────────────────────

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

      @media (hover: hover) {
        &:hover {
          color: #ccc;
        }
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

    @media (hover: hover) {
      &:hover {
        background: #2a2a2a;

        // Reveal the "..." button on row hover
        :deep(.row-action-btn) {
          opacity: 1;
          color: #888;
        }
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

  .col-actions {
    width: 32px;
    padding: 0 0.2rem;
    text-align: center;
    overflow: visible;
  }

  .col-cover {
    width: 100px;
    padding: 4px;
    vertical-align: top;
  }
}

.title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 1;
  min-width: 0;
}

// Reveal ghost flag buttons on row hover
@media (hover: hover) {
  .vrow:hover :deep(.flag-btn--row:not(.active)) {
    opacity: 0.3;
    filter: none;
  }
}

// Title cells need to be flex to keep text + buttons in line
.vc-title {
  display: flex;
  align-items: center;
}

// Grouped table title cell: wrap contents in flex div instead of making
// the <td> itself flex (flex <td> breaks table column width distribution)
.col-title-inner {
  display: flex;
  align-items: center;
}

.album-thumb {
  width: 100%;
  height: auto;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
  display: block;
}

.album-name {
  font-weight: 600;
  font-size: 0.78rem;
  color: #e0e0e0;
  margin-top: 4px;
  white-space: normal;
  line-height: 1.2;
}

.artist-name {
  font-size: 0.72rem;
  color: #aaa;
  margin-top: 2px;
  white-space: normal;
  line-height: 1.2;
}

.album-year {
  font-size: 0.7rem;
  color: #666;
  margin-top: 1px;
}

.empty-msg {
  text-align: center;
  color: #555;
  padding: 2rem;
  font-size: 0.85rem;
}

.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 499;
}

// ─── Mobile compact row layout ────────────────────────────────────────────────
// $mobile-bp must match MOBILE_BP constant in useVirtualScroll.ts

$mobile-bp: 600px;

// Cover art cell — hidden on desktop, shown on mobile as grid col 1
.vc-cover {
  display: none;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
}

.vc-thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 3px;
  display: block;
}

// Mobile subtitle (artist — album) inside title cell — hidden on desktop
.vc-mobile-sub {
  display: none;
  font-size: 0.72rem;
  color: #777;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.vc-sub-sep {
  color: #555;
}

// Teleported sort inline widget — only visible when portal is active
.mobile-sort-inline {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

// Shared sort control styles (used in the teleported inline widget)
.mobile-sort-select {
  background: #222;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.78rem;
  padding: 0.15rem 0.3rem;
  cursor: pointer;
  outline: none;
  max-width: 80px;
}

.mobile-sort-dir {
  background: #222;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.85rem;
  padding: 0.15rem 0.4rem;
  cursor: pointer;
  flex-shrink: 0;

  @media (hover: hover) {
    &:hover {
      background: #333;
    }
  }
}

@media (max-width: $mobile-bp) {
  // Hide column headers on mobile
  .vlist-header {
    display: none;
  }

  // Compact row: taller to accommodate 2-line info cell
  .vrow {
    height: 48px; // must match ROW_H_MOBILE in useVirtualScroll.ts
  }

  // Show cover art as first grid column
  .vc-cover {
    display: flex;
  }

  // Always show action button on mobile (no hover)
  :deep(.row-action-btn) {
    opacity: 1;
    color: #888;
  }

  // Move checkbox before cover art without changing DOM order
  .vc-check {
    order: -1;
  }

  // Hide desktop-only cells so they drop out of the grid flow
  .vc-drag-handle,
  .vc-artist,
  .vc-album,
  .vc-num {
    display: none;
  }

  // Title cell: stack title on top, subtitle below
  .vc-title {
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    gap: 0;
    overflow: hidden;
  }

  // Show the subtitle
  .vc-mobile-sub {
    display: block;
  }
}
</style>

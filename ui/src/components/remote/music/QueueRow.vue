<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import type { QueueEntryResponse } from '@/types/music';

const router = useRouter();

interface Props {
  entry: QueueEntryResponse;
  queueIndex: number;
  currentIndex: number;
  dropIndicator?: 'above' | 'below' | null;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  remove: [queueIndex: number];
  play: [queueIndex: number];
  dragStart: [queueIndex: number];
  dragOver: [queueIndex: number, position: 'above' | 'below'];
  dragEnd: [];
  // dropped another queue row onto this one
  dropQueue: [onto: number, position: 'above' | 'below', from: number];
  // dropped song ids onto this row
  dropSongs: [onto: number, position: 'above' | 'below', songIds: number[]];
}>();

const isPast = computed(() => props.queueIndex < props.currentIndex);
const isCurrent = computed(() => props.queueIndex === props.currentIndex);

const menuOpen = ref(false);
const btnRef = ref<HTMLButtonElement | null>(null);
const menuAbove = ref(false);

function openMenu(e: MouseEvent) {
  e.stopPropagation();
  if (menuOpen.value) {
    menuOpen.value = false;
    return;
  }
  const btn = btnRef.value;
  if (btn) {
    const rect = btn.getBoundingClientRect();
    menuAbove.value = window.innerHeight - rect.bottom < 100;
  }
  menuOpen.value = true;
}
function closeMenu() {
  menuOpen.value = false;
}
function doRemove() {
  emit('remove', props.queueIndex);
  closeMenu();
}
function goToAlbum() {
  const s = props.entry.song;
  if (s?.artist && s?.album) {
    router.push({
      path: '/remote/music/albums',
      query: { artist: s.artist, album: s.album },
    });
  }
  closeMenu();
}
function goToArtist() {
  const s = props.entry.song;
  if (s?.artist) {
    router.push({
      path: '/remote/music/artists',
      query: { artist: s.artist },
    });
  }
  closeMenu();
}

// ── Drag ─────────────────────────────────────────────────────────────────────

function onDragStart(e: DragEvent) {
  if (!e.dataTransfer) {
    return;
  }
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('application/x-queue-index', String(props.queueIndex));
  emit('dragStart', props.queueIndex);
}

function dropPosition(e: DragEvent): 'above' | 'below' {
  const el = e.currentTarget as HTMLElement;
  const rect = el.getBoundingClientRect();
  return e.clientY < rect.top + rect.height / 2 ? 'above' : 'below';
}

function onDragOver(e: DragEvent) {
  const types = e.dataTransfer?.types ?? [];
  if (
    !types.includes('application/x-queue-index') &&
    !types.includes('application/x-song-ids')
  ) {
    return;
  }
  e.preventDefault();
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = types.includes('application/x-queue-index')
      ? 'move'
      : 'copy';
  }
  emit('dragOver', props.queueIndex, dropPosition(e));
}

function onDragEnd() {
  emit('dragEnd');
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  const pos = dropPosition(e);
  const dt = e.dataTransfer;
  if (!dt) {
    return;
  }

  const queueStr = dt.getData('application/x-queue-index');
  if (queueStr !== '') {
    emit('dropQueue', props.queueIndex, pos, parseInt(queueStr, 10));
    return;
  }
  const songStr = dt.getData('application/x-song-ids');
  if (songStr !== '') {
    try {
      emit('dropSongs', props.queueIndex, pos, JSON.parse(songStr));
    } catch {
      /* ignore */
    }
  }
}
</script>

<template>
  <div
    class="queue-row"
    :class="{
      past: isPast,
      current: isCurrent,
      'drop-above': dropIndicator === 'above',
      'drop-below': dropIndicator === 'below',
    }"
    draggable="true"
    @click.self="closeMenu"
    @dblclick.self="emit('play', props.queueIndex)"
    @dragstart="onDragStart"
    @dragover="onDragOver"
    @dragend="onDragEnd"
    @drop="onDrop"
  >
    <div class="qr-cover">
      <img
        v-if="entry.song?.coverId"
        :src="`/music/cover/${entry.song.coverId}`"
        class="qr-thumb"
        loading="lazy"
        alt=""
      />
      <img v-else src="/img/no-cover.svg" class="qr-thumb" alt="" />
    </div>

    <div class="qr-info">
      <div class="qr-title" :class="{ 'now-playing': isCurrent }">
        {{ entry.song?.title ?? '(unknown)' }}
      </div>
      <div class="qr-sub" :class="{ 'now-playing-sub': isCurrent }">
        <span>{{ entry.song?.artist ?? '' }}</span>
        <template v-if="entry.song?.album">
          <span class="qr-sep">—</span>
          <span class="qr-album">{{ entry.song.album }}</span>
        </template>
      </div>
    </div>

    <div class="qr-actions-wrap">
      <button
        ref="btnRef"
        class="qr-action-btn"
        title="Actions"
        @click="openMenu"
      >
        …
      </button>
      <div
        v-if="menuOpen"
        class="qr-menu"
        :class="{ above: menuAbove }"
        @click.stop
      >
        <button :disabled="!entry.song?.album" @click="goToAlbum">
          Go to Album
        </button>
        <button :disabled="!entry.song?.artist" @click="goToArtist">
          Go to Artist
        </button>
        <hr />
        <button class="danger" @click="doRemove">Remove from Queue</button>
      </div>
      <div v-if="menuOpen" class="qr-menu-overlay" @click="closeMenu" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.queue-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.4rem;
  border-radius: 4px;
  transition: background 0.1s;
  position: relative;
  cursor: grab;
  border-top: 2px solid transparent;
  border-bottom: 2px solid transparent;

  &:hover {
    background: #222;
  }
  &.past {
    opacity: 0.4;
  }
  &.current {
    background: #1a2e1a;
    border-left: 2px solid #4ade80;
    padding-left: calc(0.4rem - 2px);
  }
  &.drop-above {
    border-top-color: #3b82f6;
  }
  &.drop-below {
    border-bottom-color: #3b82f6;
  }
}

.qr-cover {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  pointer-events: none;
}
.qr-thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 3px;
  display: block;
}
.qr-info {
  flex: 1;
  min-width: 0;
  pointer-events: none;
}

.qr-title {
  font-size: 0.8rem;
  color: #e0e0e0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  &.now-playing {
    font-weight: 600;
    color: #4ade80;
  }
}

.qr-sub {
  font-size: 0.72rem;
  color: #777;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  &.now-playing-sub {
    color: #86efac;
  }
}

.qr-sep {
  margin: 0 0.2rem;
  color: #555;
}
.qr-album {
  color: #666;
}
.qr-actions-wrap {
  flex-shrink: 0;
  position: relative;
}

.qr-action-btn {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  padding: 0.15rem 0.3rem;
  border-radius: 3px;
  font-size: 1rem;
  line-height: 1;
  &:hover {
    background: #333;
    color: #ccc;
  }
}

.qr-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.25rem 0;
  z-index: 200;
  min-width: 130px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
  white-space: nowrap;
  &.above {
    top: auto;
    bottom: calc(100% + 4px);
  }
  button {
    display: block;
    width: 100%;
    background: none;
    border: none;
    color: #e0e0e0;
    padding: 0.35rem 0.7rem;
    text-align: left;
    font-size: 0.82rem;
    cursor: pointer;
    &:hover {
      background: #3b82f6;
      color: #fff;
    }
    &.danger {
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

.qr-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 199;
}
</style>

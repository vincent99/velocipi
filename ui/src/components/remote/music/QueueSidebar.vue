<script setup lang="ts">
import { ref, computed } from 'vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useDeviceState } from '@/composables/useDeviceState';
import QueueRow from '@/components/remote/music/QueueRow.vue';
import LyricsPanel from '@/components/remote/music/LyricsPanel.vue';

defineProps<{
  mobileOpen: boolean;
  width: number;
}>();

defineEmits<{ close: [] }>();

const sidebarTab = ref<'queue' | 'lyrics'>('queue');

const {
  musicState,
  appendQueue,
  removeFromQueue,
  jumpToIndex,
  moveInQueue,
  clearQueue,
  undoQueueChange,
} = useMusicPlayer();

const { musicQueue } = useDeviceState();

const queuePosition = computed(() => {
  const q = musicQueue.value;
  if (!q || q.entries.length === 0) {
    return '';
  }
  return `${q.currentIndex + 1} of ${q.entries.length}`;
});

const queueTotalDuration = computed(() => {
  const entries = musicQueue.value?.entries ?? [];
  const total = entries.reduce((sum, e) => sum + (e.song?.length ?? 0), 0);
  return formatDuration(total);
});

function formatDuration(sec: number): string {
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${ss.toString().padStart(2, '0')}`;
  }
  return `${m}:${ss.toString().padStart(2, '0')}`;
}

async function handleQueueRemove(queueIndex: number) {
  await removeFromQueue(queueIndex);
}

function handleQueuePlay(queueIndex: number) {
  jumpToIndex(queueIndex);
}

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
      e.dataTransfer.dropEffect = 'copy';
    }
  }
}

async function insertSongsAtQueuePosition(
  songIds: number[],
  afterIndex: number
) {
  const totalBefore = musicQueue.value?.entries.length ?? 0;
  await appendQueue(songIds);
  const numNew = songIds.length;
  const totalAfterAppend = totalBefore + numNew;
  for (let i = 0; i < numNew; i++) {
    const fromIdx = totalAfterAppend - numNew + i;
    const toIdx = afterIndex + 1 + i;
    if (fromIdx !== toIdx) {
      await moveInQueue(fromIdx, toIdx);
    }
  }
}
</script>

<template>
  <div
    class="music-sidebar-right"
    :class="{ 'mobile-open': mobileOpen }"
    :style="{ width: width + 'px' }"
  >
    <div class="sidebar-heading">
      <div class="sidebar-tabs">
        <button
          class="sidebar-tab"
          :class="{ 'sidebar-tab--active': sidebarTab === 'queue' }"
          @click="sidebarTab = 'queue'"
        >
          Queue
        </button>
        <button
          class="sidebar-tab"
          :class="{ 'sidebar-tab--active': sidebarTab === 'lyrics' }"
          @click="sidebarTab = 'lyrics'"
        >
          Lyrics
        </button>
      </div>
      <button class="mobile-queue-close" @click="$emit('close')">✕</button>
    </div>

    <!-- Queue tab -->
    <template v-if="sidebarTab === 'queue'">
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
      <div class="queue-footer">
        <div class="queue-footer-info">
          <span v-if="queuePosition" class="queue-position">{{
            queuePosition
          }}</span>
          <span v-if="queueTotalDuration" class="queue-total-duration">{{
            queueTotalDuration
          }}</span>
        </div>
        <div class="queue-footer-actions">
          <button
            class="queue-footer-btn"
            title="Undo queue change"
            @click="undoQueueChange()"
          >
            Undo
          </button>
          <button
            class="queue-footer-btn queue-footer-btn--danger"
            title="Clear queue"
            @click="clearQueue()"
          >
            Clear
          </button>
        </div>
      </div>
    </template>

    <!-- Lyrics tab -->
    <LyricsPanel v-else-if="sidebarTab === 'lyrics'" />
  </div>
</template>

<style scoped lang="scss">
.music-sidebar-right {
  // width set via inline style
  flex-shrink: 0;
  background: #161616;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  min-width: 60px;
}

.sidebar-heading {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.sidebar-tabs {
  display: flex;
  flex: 1;
  min-width: 0;
}

.sidebar-tab {
  flex: 1;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  color: #555;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
  transition:
    color 0.15s,
    border-color 0.15s;

  &:hover {
    color: #999;
  }

  &--active {
    color: #90caf9;
    border-bottom-color: #3b82f6;
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

.queue-footer {
  flex-shrink: 0;
  border-top: 1px solid #2a2a2a;
  padding: 0.3rem 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.queue-footer-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.queue-position {
  font-size: 0.7rem;
  color: #666;
  white-space: nowrap;
}

.queue-total-duration {
  font-size: 0.7rem;
  color: #555;
  white-space: nowrap;
}

.queue-footer-actions {
  display: flex;
  gap: 0.3rem;
  flex-shrink: 0;
}

.queue-footer-btn {
  background: #222;
  border: 1px solid #333;
  border-radius: 3px;
  color: #888;
  font-size: 0.68rem;
  padding: 0.2rem 0.45rem;
  cursor: pointer;
  white-space: nowrap;

  &:hover {
    background: #2a2a2a;
    color: #bbb;
    border-color: #444;
  }

  &--danger:hover {
    color: #f87171;
    border-color: #7f1d1d;
  }
}

.mobile-queue-close {
  display: none;
}

$mobile-bp: 600px;

@media (max-width: $mobile-bp) {
  .music-sidebar-right {
    position: absolute;
    z-index: 200;
    top: 0;
    right: 0;
    bottom: 0;
    left: 0;
    width: auto !important;
    min-width: 0;
    transform: translateX(100%);
    transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);

    &.mobile-open {
      transform: translateX(0);
    }
  }

  .mobile-queue-close {
    display: block;
    margin-left: auto;
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    font-size: 0.85rem;
    padding: 0 0.25rem;
    line-height: 1;

    &:hover {
      color: #ccc;
    }
  }
}
</style>

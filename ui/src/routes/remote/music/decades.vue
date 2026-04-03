<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import SongTable from '@/components/remote/music/SongTable.vue';
import QueueActionButton from '@/components/remote/music/QueueActionButton.vue';
import ItemContextMenu from '@/components/remote/music/ItemContextMenu.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Decade, Song } from '@/types/music';

const route = useRoute();
const router = useRouter();
const { markSong, favoriteSong } = useMusicPlayer();
const { openEdit } = useSongEdit();

function handleEdit(ids: number[]) {
  const decade = selectedDecade.value;
  openEdit(
    decadeSongs.value.filter((s) => ids.includes(s.id)),
    () => {
      if (decade) {
        loadDecadeSongs(decade);
      }
    }
  );
}

const decades = ref<Decade[]>([]);
const loading = ref(false);
const decadeSongs = ref<Song[]>([]);
const decadeSongsLoading = ref(false);

// Derive selected decade purely from URL query param
const selectedDecade = computed(() => {
  const qDecade = route.query.decade as string | undefined;
  if (!qDecade) {
    return null;
  }
  const n = parseInt(qDecade, 10);
  return decades.value.find((d) => d.decade === n) ?? null;
});

async function load() {
  loading.value = true;
  try {
    const r = await fetch('/music/decades');
    if (r.ok) {
      decades.value = await r.json();
    }
  } finally {
    loading.value = false;
  }
}

load();

async function loadDecadeSongs(decade: Decade) {
  decadeSongsLoading.value = true;
  try {
    const params = new URLSearchParams({ decade: String(decade.decade) });
    const r = await fetch(`/music/songs?${params}`);
    if (r.ok) {
      const data = await r.json();
      decadeSongs.value = data.songs ?? [];
    }
  } finally {
    decadeSongsLoading.value = false;
  }
}

// Load decade songs whenever the selection changes
watch(
  selectedDecade,
  async (decade) => {
    if (!decade) {
      decadeSongs.value = [];
      return;
    }
    await loadDecadeSongs(decade);
  },
  { immediate: true }
);

function selectDecade(decade: Decade) {
  router.push({ query: { decade: String(decade.decade) } });
}

function backToGrid() {
  router.push({ query: {} });
}

const decadeSongIds = computed(() => decadeSongs.value.map((s) => s.id));

const ctxMenu = ref<{ ids: number[] | null; x: number; y: number } | null>(
  null
);

async function onDecadeContextMenu(decade: Decade, e: MouseEvent) {
  if (e.metaKey || e.ctrlKey) {
    return;
  }
  e.preventDefault();
  ctxMenu.value = { ids: null, x: e.clientX, y: e.clientY };
  const r = await fetch(`/music/songs?decade=${decade.decade}`);
  if (r.ok && ctxMenu.value) {
    const data = await r.json();
    const songs: Song[] = data.songs ?? data;
    ctxMenu.value.ids = songs.map((s) => s.id);
  }
}

function decadeLabel(d: number): string {
  return d > 0 ? `${d}s` : 'Unknown';
}

async function handleMark(ids: number[], marked: boolean) {
  await Promise.all(ids.map((id) => markSong(id, marked)));
}

async function handleFavorite(ids: number[], favorite: boolean) {
  await Promise.all(ids.map((id) => favoriteSong(id, favorite)));
}

async function handleDelete(ids: number[]) {
  await fetch('/music/songs/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  decadeSongs.value = decadeSongs.value.filter((s) => !ids.includes(s.id));
}
</script>

<template>
  <div class="decades-view">
    <!-- Decade detail -->
    <template v-if="selectedDecade">
      <div
        class="detail-header"
        @contextmenu="
          (e) => {
            if (!e.metaKey && !e.ctrlKey) {
              e.preventDefault();
              ctxMenu = { ids: decadeSongIds, x: e.clientX, y: e.clientY };
            }
          }
        "
      >
        <button class="back-btn" @click="backToGrid">← Decades</button>
        <div class="detail-info">
          <div class="detail-name">
            {{ decadeLabel(selectedDecade.decade) }}
          </div>
          <div class="detail-meta">
            {{ selectedDecade.trackCount }} track{{
              selectedDecade.trackCount === 1 ? '' : 's'
            }}
          </div>
        </div>
        <div class="detail-actions">
          <QueueActionButton :ids="decadeSongIds" variant="detail" />
        </div>
      </div>
      <SongTable
        :songs="decadeSongs"
        :loading="decadeSongsLoading"
        @mark="handleMark"
        @favorite="handleFavorite"
        @delete="handleDelete"
        @edit="handleEdit"
      />
    </template>

    <!-- Decade grid -->
    <template v-else>
      <div v-if="loading" class="grid-loading">Loading…</div>
      <div v-else class="decade-grid">
        <div
          v-for="decade in decades"
          :key="decade.decade"
          class="decade-card"
          @click="selectDecade(decade)"
          @contextmenu="onDecadeContextMenu(decade, $event)"
        >
          <div class="decade-label">{{ decadeLabel(decade.decade) }}</div>
          <div class="decade-count">{{ decade.trackCount }} tracks</div>
          <button
            class="card-menu-btn"
            title="Actions"
            @click.stop="onDecadeContextMenu(decade, $event)"
          >
            …
          </button>
        </div>
        <div v-if="decades.length === 0" class="grid-empty">
          No decades found.
        </div>
      </div>
    </template>
    <ItemContextMenu
      v-if="ctxMenu"
      :x="ctxMenu.x"
      :y="ctxMenu.y"
      :ids="ctxMenu.ids"
      @close="ctxMenu = null"
    />
  </div>
</template>

<style scoped lang="scss">
.decades-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.grid-loading,
.grid-empty {
  color: #555;
  text-align: center;
  padding: 2rem;
}

.decade-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.75rem;
  overflow-y: auto;
  flex: 1;
  align-content: flex-start;
}

.decade-card {
  position: relative;
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 0.75rem 1.25rem;
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s;
  min-width: 90px;
  text-align: center;

  &:hover {
    background: #222;
    border-color: #3b82f6;

    .card-menu-btn {
      opacity: 1;
    }
  }
}

.decade-label {
  font-size: 1.1rem;
  font-weight: 700;
  color: #e0e0e0;
}

.decade-count {
  font-size: 0.72rem;
  color: #666;
  margin-top: 2px;
}

.card-menu-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 0.9rem;
  line-height: 1;
  opacity: 0;

  &:hover {
    background: #333;
    color: #ccc;
  }

  @media (hover: none) {
    opacity: 1;
    color: #888;
  }
}

.detail-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.75rem;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.back-btn {
  background: none;
  border: 1px solid #444;
  color: #aaa;
  border-radius: 4px;
  padding: 0.3rem 0.6rem;
  font-size: 0.8rem;
  cursor: pointer;
  align-self: center;

  &:hover {
    background: #222;
    color: #e0e0e0;
  }
}

.detail-info {
  flex: 1;
}

.detail-name {
  font-weight: 700;
  font-size: 1rem;
  color: #e0e0e0;
}

.detail-meta {
  font-size: 0.8rem;
  color: #888;
  margin-top: 2px;
}

.detail-actions {
  display: flex;
  gap: 0.4rem;
  flex-shrink: 0;
  align-self: center;

  button {
    background: #1e3a5f;
    border: 1px solid #2a5a9f;
    color: #90caf9;
    border-radius: 4px;
    padding: 0.25rem 0.6rem;
    font-size: 0.78rem;
    cursor: pointer;

    &:hover {
      background: #2a4a7f;
    }
  }
}
</style>

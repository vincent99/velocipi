<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import SongTable from '@/components/remote/music/SongTable.vue';
import QueueActionButton from '@/components/remote/music/QueueActionButton.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Genre, Song } from '@/types/music';

const route = useRoute();
const router = useRouter();
const { markSong, favoriteSong } = useMusicPlayer();
const { openEdit } = useSongEdit();

function handleEdit(ids: number[]) {
  const genre = selectedGenre.value;
  openEdit(
    genreSongs.value.filter((s) => ids.includes(s.id)),
    () => {
      if (genre) {
        loadGenreSongs(genre);
      }
    }
  );
}

const genres = ref<Genre[]>([]);
const loading = ref(false);
const genreSongs = ref<Song[]>([]);
const genreSongsLoading = ref(false);

// Derive selected genre purely from URL query param
const selectedGenre = computed(() => {
  const qGenre = route.query.genre as string | undefined;
  if (!qGenre) {
    return null;
  }
  return genres.value.find((g) => g.genre === qGenre) ?? null;
});

async function load() {
  loading.value = true;
  try {
    const r = await fetch('/music/genres');
    if (r.ok) {
      genres.value = await r.json();
    }
  } finally {
    loading.value = false;
  }
}

load();

async function loadGenreSongs(genre: Genre) {
  genreSongsLoading.value = true;
  try {
    const params = new URLSearchParams({ genre: genre.genre });
    const r = await fetch(`/music/songs?${params}`);
    if (r.ok) {
      const data = await r.json();
      genreSongs.value = data.songs ?? [];
    }
  } finally {
    genreSongsLoading.value = false;
  }
}

// Load genre songs whenever the selection changes
watch(
  selectedGenre,
  async (genre) => {
    if (!genre) {
      genreSongs.value = [];
      return;
    }
    await loadGenreSongs(genre);
  },
  { immediate: true }
);

function selectGenre(genre: Genre) {
  router.push({ query: { genre: genre.genre } });
}

function backToGrid() {
  router.push({ query: {} });
}

const genreSongIds = computed(() => genreSongs.value.map((s) => s.id));

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
  genreSongs.value = genreSongs.value.filter((s) => !ids.includes(s.id));
}
</script>

<template>
  <div class="genres-view">
    <!-- Genre detail -->
    <template v-if="selectedGenre">
      <div class="detail-header">
        <button class="back-btn" @click="backToGrid">← Genres</button>
        <div class="detail-info">
          <div class="detail-name">{{ selectedGenre.genre }}</div>
          <div class="detail-meta">
            {{ selectedGenre.trackCount }} track{{
              selectedGenre.trackCount === 1 ? '' : 's'
            }}
          </div>
        </div>
        <div class="detail-actions">
          <QueueActionButton :ids="genreSongIds" variant="detail" />
        </div>
      </div>
      <SongTable
        :songs="genreSongs"
        :loading="genreSongsLoading"
        @mark="handleMark"
        @favorite="handleFavorite"
        @delete="handleDelete"
        @edit="handleEdit"
      />
    </template>

    <!-- Genre grid -->
    <template v-else>
      <div v-if="loading" class="grid-loading">Loading…</div>
      <div v-else class="genre-grid">
        <div
          v-for="genre in genres"
          :key="genre.genre"
          class="genre-card"
          @click="selectGenre(genre)"
        >
          <div class="genre-name">{{ genre.genre }}</div>
          <div class="genre-count">{{ genre.trackCount }} tracks</div>
        </div>
        <div v-if="genres.length === 0" class="grid-empty">
          No genres found.
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.genres-view {
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

.genre-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.75rem;
  overflow-y: auto;
  flex: 1;
  align-content: flex-start;
}

.genre-card {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 0.6rem 1rem;
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s;
  min-width: 100px;

  &:hover {
    background: #222;
    border-color: #3b82f6;
  }
}

.genre-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: #e0e0e0;
}

.genre-count {
  font-size: 0.72rem;
  color: #666;
  margin-top: 2px;
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

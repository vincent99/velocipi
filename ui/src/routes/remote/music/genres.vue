<script setup lang="ts">
import { ref } from 'vue';
import SongTable from '@/components/remote/SongTable.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Genre, Song } from '@/types/music';

const { enqueue, appendQueue, replaceQueue, markSong } = useMusicPlayer();
const { openEdit } = useSongEdit();

function handleEdit(ids: number[]) {
  openEdit(genreSongs.value.filter((s) => ids.includes(s.id)));
}

const genres = ref<Genre[]>([]);
const loading = ref(false);
const selectedGenre = ref<Genre | null>(null);
const genreSongs = ref<Song[]>([]);
const genreSongsLoading = ref(false);

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

async function selectGenre(genre: Genre) {
  selectedGenre.value = genre;
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

function backToGrid() {
  selectedGenre.value = null;
  genreSongs.value = [];
}

function genreSongIds() {
  return genreSongs.value.map((s) => s.id);
}

async function handleMark(ids: number[], marked: boolean) {
  await Promise.all(ids.map((id) => markSong(id, marked)));
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
          <div class="detail-actions">
            <button @click="replaceQueue(genreSongIds())">Play</button>
            <button @click="enqueue(genreSongIds())">Enqueue</button>
            <button @click="appendQueue(genreSongIds())">Append</button>
          </div>
        </div>
      </div>
      <SongTable
        :songs="genreSongs"
        :loading="genreSongsLoading"
        @enqueue="(ids) => enqueue(ids)"
        @append="(ids) => appendQueue(ids)"
        @replace="(ids) => replaceQueue(ids)"
        @mark="handleMark"
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
  margin-top: 0.5rem;

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

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import SongTable from '@/components/remote/SongTable.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Song } from '@/types/music';

const route = useRoute();
const { enqueue, appendQueue, replaceQueue, markSong, favoriteSong } =
  useMusicPlayer();
const { openEdit } = useSongEdit();

function handleEdit(ids: number[]) {
  openEdit(
    songs.value.filter((s) => ids.includes(s.id)),
    () => load(currentQuery.value)
  );
}

const songs = ref<Song[]>([]);
const loading = ref(false);
const currentQuery = ref('');

async function load(q: string) {
  if (!q) {
    songs.value = [];
    currentQuery.value = '';
    return;
  }
  currentQuery.value = q;
  loading.value = true;
  try {
    const params = new URLSearchParams({ search: q });
    const r = await fetch(`/music/songs?${params}`);
    if (r.ok) {
      const data = await r.json();
      songs.value = data.songs ?? [];
    }
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.query.q as string | undefined,
  (q) => load(q ?? ''),
  { immediate: true }
);

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
  songs.value = songs.value.filter((s) => !ids.includes(s.id));
}
</script>

<template>
  <div class="search-view">
    <div v-if="currentQuery" class="search-heading">
      Results for <em>{{ currentQuery }}</em>
    </div>
    <div v-else class="search-empty">Enter a search term above.</div>
    <SongTable
      v-if="currentQuery"
      :songs="songs"
      :loading="loading"
      @enqueue="(ids) => enqueue(ids)"
      @append="(ids) => appendQueue(ids)"
      @replace="(ids) => replaceQueue(ids)"
      @mark="handleMark"
      @favorite="handleFavorite"
      @delete="handleDelete"
      @edit="handleEdit"
    />
  </div>
</template>

<style scoped lang="scss">
.search-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.search-heading {
  padding: 0.5rem 0.75rem;
  font-size: 0.82rem;
  color: #888;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;

  em {
    color: #e0e0e0;
    font-style: normal;
    font-weight: 600;
  }
}

.search-empty {
  padding: 2rem;
  text-align: center;
  color: #555;
  font-size: 0.85rem;
}
</style>

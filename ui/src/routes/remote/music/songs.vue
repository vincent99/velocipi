<script setup lang="ts">
import { ref } from 'vue';
import SongTable from '@/components/remote/music/SongTable.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Song } from '@/types/music';

const { markSong, favoriteSong } = useMusicPlayer();
const { openEdit } = useSongEdit();

function handleEdit(ids: number[]) {
  openEdit(
    songs.value.filter((s) => ids.includes(s.id)),
    load
  );
}

async function handleDelete(ids: number[]) {
  await fetch('/music/songs/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  songs.value = songs.value.filter((s) => !ids.includes(s.id));
}

const songs = ref<Song[]>([]);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const r = await fetch('/music/songs');
    if (r.ok) {
      const data = await r.json();
      songs.value = data.songs ?? [];
    }
  } finally {
    loading.value = false;
  }
}

load();

async function handleMark(ids: number[], marked: boolean) {
  await Promise.all(ids.map((id) => markSong(id, marked)));
}

async function handleFavorite(ids: number[], favorite: boolean) {
  await Promise.all(ids.map((id) => favoriteSong(id, favorite)));
}
</script>

<template>
  <SongTable
    :songs="songs"
    :loading="loading"
    @mark="handleMark"
    @favorite="handleFavorite"
    @delete="handleDelete"
    @edit="handleEdit"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue';
import SongTable from '@/components/remote/SongTable.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Song } from '@/types/music';

const { enqueue, appendQueue, replaceQueue, markSong } = useMusicPlayer();
const { openEdit } = useSongEdit();

function handleEdit(ids: number[]) {
  openEdit(songs.value.filter((s) => ids.includes(s.id)));
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
</script>

<template>
  <SongTable
    :songs="songs"
    :loading="loading"
    @enqueue="(ids) => enqueue(ids)"
    @append="(ids) => appendQueue(ids)"
    @replace="(ids) => replaceQueue(ids)"
    @mark="handleMark"
    @delete="handleDelete"
    @edit="handleEdit"
  />
</template>

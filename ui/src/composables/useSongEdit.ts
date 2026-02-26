import { ref } from 'vue';
import type { Song } from '@/types/music';

// Module-level singleton so all components share the same modal state.
const editingSongs = ref<Song[]>([]);

export function useSongEdit() {
  function openEdit(songs: Song[]) {
    editingSongs.value = songs;
  }

  function closeEdit() {
    editingSongs.value = [];
  }

  async function saveEdit(ids: number[], fields: Record<string, unknown>) {
    await fetch('/music/songs/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, fields }),
    });
    closeEdit();
  }

  return { editingSongs, openEdit, closeEdit, saveEdit };
}

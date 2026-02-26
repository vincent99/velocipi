import { ref } from 'vue';
import { useSongStore } from '@/composables/useSongStore';
import type { Song } from '@/types/music';

// Module-level singleton so all components share the same modal state.
const editingSongs = ref<Song[]>([]);
const saving = ref(false);
let afterSave: (() => void) | null = null;

export function useSongEdit() {
  function openEdit(songs: Song[], onAfterSave?: () => void) {
    editingSongs.value = songs;
    afterSave = onAfterSave ?? null;
  }

  function closeEdit() {
    editingSongs.value = [];
    afterSave = null;
  }

  async function saveEdit(ids: number[], fields: Record<string, unknown>) {
    saving.value = true;
    try {
      const r = await fetch('/music/songs/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, fields }),
      });
      if (r.ok) {
        // Immediately reflect the edited fields in the store so all components
        // update without waiting for a full reload.
        const { patch } = useSongStore();
        for (const id of ids) {
          patch(id, fields as Partial<Song>);
        }
      }
      const cb = afterSave;
      closeEdit();
      cb?.();
    } finally {
      saving.value = false;
    }
  }

  return { editingSongs, saving, openEdit, closeEdit, saveEdit };
}

import { reactive } from 'vue';
import type { Song } from '@/types/music';

// Module-level reactive map: song id → partial overrides applied on top of the
// server-fetched Song object.  Any component that writes here (mark, favorite,
// metadata edit) immediately updates every other component that calls resolve().
const overrides = reactive(new Map<number, Partial<Song>>());

export function useSongStore() {
  /** Merge a server-fetched Song with any locally-stored overrides. */
  function resolve(song: Song): Song {
    const patch = overrides.get(song.id);
    return patch ? { ...song, ...patch } : song;
  }

  /** Write one or more fields for a song into the override store. */
  function patch(id: number, fields: Partial<Song>) {
    const existing = overrides.get(id);
    if (existing) {
      Object.assign(existing, fields);
    } else {
      overrides.set(id, { ...fields });
    }
  }

  return { resolve, patch };
}

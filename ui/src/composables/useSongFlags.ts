import { reactive } from 'vue';

// Module-level reactive overlay: maps song id → { marked, favorite }
// Any component can read from this to get the latest flag state,
// overriding whatever came from the server in the Song object.
const overlay = reactive(
  new Map<number, { marked: boolean; favorite: boolean }>()
);

export function useSongFlags() {
  function setFlag(id: number, field: 'marked' | 'favorite', value: boolean) {
    const existing = overlay.get(id);
    if (existing) {
      existing[field] = value;
    } else {
      overlay.set(id, { marked: false, favorite: false, [field]: value });
    }
  }

  function getMarked(id: number, fallback: boolean): boolean {
    const entry = overlay.get(id);
    return entry !== undefined ? entry.marked : fallback;
  }

  function getFavorite(id: number, fallback: boolean): boolean {
    const entry = overlay.get(id);
    return entry !== undefined ? entry.favorite : fallback;
  }

  return { overlay, setFlag, getMarked, getFavorite };
}

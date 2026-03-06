import { ref, computed, watch } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import type { LyricLine } from '@/types/music';

// Module-level singleton state
const lines = ref<LyricLine[]>([]);
const currentIndex = ref(-1);
const loading = ref(false);
const lyricsCache = new Map<number, LyricLine[]>();
let lyricsInitialised = false;

function initLyrics() {
  if (lyricsInitialised) {
    return;
  }
  lyricsInitialised = true;

  const { musicState } = useDeviceState();

  // Clear and reload lyrics whenever the current song changes.
  // immediate: true so that a song already playing when this page loads
  // triggers a fetch (the watch won't fire on change alone in that case).
  watch(
    () => musicState.value?.currentSongId,
    async (id) => {
      // Always clear immediately so stale lyrics from the previous song
      // are never shown for the incoming song.
      lines.value = [];
      currentIndex.value = -1;

      if (id == null) {
        loading.value = false;
        return;
      }

      const cached = lyricsCache.get(id);
      if (cached) {
        lines.value = cached;
        loading.value = false;
        return;
      }

      loading.value = true;
      try {
        const r = await fetch(`/music/songs/${id}/lyrics`);
        if (!r.ok) {
          loading.value = false;
          return;
        }
        const data: { lines: LyricLine[] } = await r.json();
        const fetched = data.lines ?? [];
        lyricsCache.set(id, fetched);
        lines.value = fetched;
      } catch {
        // leave lines empty — "No lyrics" will be shown
      } finally {
        loading.value = false;
      }
    },
    { immediate: true }
  );

  // Advance the active lyric line only while the song is playing.
  watch(
    () =>
      musicState.value?.status === 'playing'
        ? musicState.value.elapsedSec
        : null,
    (elapsed) => {
      if (elapsed == null || lines.value.length === 0) {
        return;
      }
      let lo = 0;
      let hi = lines.value.length - 1;
      let result = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (lines.value[mid].timeSec <= elapsed) {
          result = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }
      currentIndex.value = result;
    }
  );
}

export function useLyrics() {
  initLyrics();
  const { musicState } = useDeviceState();
  const hasLyrics = computed(() => lines.value.length > 0);
  const isPlaying = computed(() => musicState.value?.status === 'playing');
  return {
    currentLines: lines,
    currentIndex,
    hasLyrics,
    loading,
    isPlaying,
  };
}

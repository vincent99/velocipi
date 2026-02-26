import { ref, computed, watch } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import { useWebSocket } from '@/composables/useWebSocket';
import { useSongStore } from '@/composables/useSongStore';
import type { MusicControlMsg } from '@/types/ws';
import type { Song } from '@/types/music';

// Module-level singleton — raw fetched song for the currently playing track.
const _currentSongBase = ref<Song | null>(null);
const songCache = new Map<number, Song>();

let playerInitialised = false;

function initPlayer() {
  if (playerInitialised) {
    return;
  }
  playerInitialised = true;

  const { musicState } = useDeviceState();

  watch(
    () => musicState.value?.currentSongId,
    async (id) => {
      if (id == null) {
        _currentSongBase.value = null;
        return;
      }
      const cached = songCache.get(id);
      if (cached) {
        _currentSongBase.value = cached;
        return;
      }
      try {
        const r = await fetch(`/music/songs/${id}`);
        if (!r.ok) {
          return;
        }
        const song: Song = await r.json();
        songCache.set(id, song);
        _currentSongBase.value = song;
      } catch {
        // ignore fetch errors
      }
    }
  );
}

export function useMusicPlayer() {
  initPlayer();

  const { musicState } = useDeviceState();
  const { send } = useWebSocket();
  const { resolve, patch } = useSongStore();

  // Expose currentSong as a computed so store overrides propagate reactively.
  const currentSong = computed(() =>
    _currentSongBase.value ? resolve(_currentSongBase.value) : null
  );

  function control(
    action: MusicControlMsg['action'],
    value?: number,
    str?: string
  ) {
    const msg: MusicControlMsg = { type: 'musicControl', action };
    if (value !== undefined) {
      msg.value = value;
    }
    if (str !== undefined) {
      msg.str = str;
    }
    send(msg);
  }

  return {
    musicState,
    currentSong,
    control,
    play: () => control('play'),
    pause: () => control('pause'),
    stop: () => control('stop'),
    next: () => control('next'),
    prev: () => control('prev'),
    seek: (sec: number) => control('seek', sec),
    skipForward: (sec: number) => control('skipForward', sec),
    skipBack: (sec: number) => control('skipBack', sec),
    setVolume: (vol: number) => control('setVolume', vol),
    setShuffle: (on: boolean) => control('setShuffle', undefined, String(on)),
    setRepeat: (mode: 'off' | 'song' | 'queue') =>
      control('setRepeat', undefined, mode),
    jumpToIndex: (index: number) => control('jumpToIndex', index),
    replaceQueue: (ids: number[]) =>
      fetch('/music/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ songIds: ids }),
      }),
    enqueue: (ids: number[]) =>
      fetch('/music/queue/enqueue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ songIds: ids }),
      }),
    appendQueue: (ids: number[]) =>
      fetch('/music/queue/append', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ songIds: ids }),
      }),
    markSong: async (id: number, marked: boolean) => {
      const r = await fetch(`/music/songs/${id}/mark`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ marked }),
      });
      if (r.ok) {
        patch(id, { marked });
        const cached = songCache.get(id);
        if (cached) {
          cached.marked = marked;
        }
      }
      return r;
    },
    favoriteSong: async (id: number, favorite: boolean) => {
      const r = await fetch(`/music/songs/${id}/favorite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ favorite }),
      });
      if (r.ok) {
        patch(id, { favorite });
        const cached = songCache.get(id);
        if (cached) {
          cached.favorite = favorite;
        }
      }
      return r;
    },
    removeFromQueue: (index: number) =>
      fetch('/music/queue/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index }),
      }),
    moveInQueue: (from: number, to: number) =>
      fetch('/music/queue/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from, to }),
      }),
  };
}

import { ref, watch } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import { useWebSocket } from '@/composables/useWebSocket';
import type { MusicControlMsg } from '@/types/ws';
import type { Song } from '@/types/music';

// Module-level singleton — fetched song detail for the currently playing song.
const currentSong = ref<Song | null>(null);
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
        currentSong.value = null;
        return;
      }
      const cached = songCache.get(id);
      if (cached) {
        currentSong.value = cached;
        return;
      }
      try {
        const r = await fetch(`/music/songs/${id}`);
        if (!r.ok) {
          return;
        }
        const song: Song = await r.json();
        songCache.set(id, song);
        currentSong.value = song;
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
    markSong: (id: number, marked: boolean) =>
      fetch(`/music/songs/${id}/mark`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ marked }),
      }),
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

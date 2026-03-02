import { ref, computed, type Ref } from 'vue';
import { useSongStore } from '@/composables/useSongStore';
import type { Song } from '@/types/music';

export type SortCol =
  | 'artist'
  | 'album'
  | 'year'
  | 'title'
  | 'track'
  | 'duration';

export interface AlbumGroup {
  key: string;
  artist: string;
  album: string;
  coverId: number | null;
  year: number;
  songs: Song[];
  startIndex: number;
}

export function useSongSort(
  songs: () => Song[],
  albumContext: () => boolean,
  groupByAlbum: () => boolean,
  playlistMode: () => boolean,
  scrollEl: Ref<HTMLElement | null>,
  scrollTop: Ref<number>
) {
  const { resolve } = useSongStore();

  const sortCol = ref<SortCol>(albumContext() ? 'track' : 'artist');
  const sortDir = ref<1 | -1>(1);
  // 'album' = just album name, 'artistAlbum' = artist then album
  const albumSortMode = ref<'album' | 'artistAlbum'>('album');

  function resetScroll() {
    if (scrollEl.value) {
      scrollEl.value.scrollTop = 0;
    }
    scrollTop.value = 0;
  }

  function cycleSort(col: SortCol) {
    if (col === 'album') {
      if (sortCol.value !== 'album') {
        sortCol.value = 'album';
        sortDir.value = 1;
        albumSortMode.value = 'album';
      } else if (albumSortMode.value === 'album') {
        albumSortMode.value = 'artistAlbum';
      } else {
        sortDir.value = sortDir.value === 1 ? -1 : 1;
        albumSortMode.value = 'album';
      }
    } else {
      if (sortCol.value === col) {
        sortDir.value = sortDir.value === 1 ? -1 : 1;
      } else {
        sortCol.value = col;
        sortDir.value = 1;
      }
    }
    resetScroll();
  }

  function albumColLabel(): string {
    if (sortCol.value === 'album' && albumSortMode.value === 'artistAlbum') {
      return 'Album by Artist';
    }
    return 'Album';
  }

  function sortIndicator(col: SortCol): string {
    if (sortCol.value !== col) {
      return '';
    }
    return sortDir.value === 1 ? ' ↑' : ' ↓';
  }

  function sortValue(song: Song): string | number {
    switch (sortCol.value) {
      case 'artist':
        return (song.artistSort || song.artist).toLowerCase();
      case 'album':
        if (albumSortMode.value === 'artistAlbum') {
          return (
            (song.artistSort || song.artist) +
            '\0' +
            (song.albumSort || song.album)
          ).toLowerCase();
        }
        return (song.albumSort || song.album).toLowerCase();
      case 'year':
        return song.year || 0;
      case 'title':
        return song.title.toLowerCase();
      case 'track':
        return song.discNumber * 10000 + song.trackNumber;
      case 'duration':
        return song.length;
    }
  }

  const sortedSongs = computed<Song[]>(() => {
    // In playlist mode preserve the original order; sorting is disabled
    if (playlistMode()) {
      return songs();
    }
    const d = sortDir.value;
    return [...songs()].sort((a, b) => {
      const av = sortValue(a);
      const bv = sortValue(b);
      if (av < bv) {
        return -d;
      }
      if (av > bv) {
        return d;
      }
      return 0;
    });
  });

  // Apply store overrides to all sorted songs so any field change (mark, favorite,
  // title, artist, etc.) propagates to every row without a full data reload.
  const resolvedSongs = computed<Song[]>(() => sortedSongs.value.map(resolve));

  const albumGroups = computed<AlbumGroup[]>(() => {
    if (!groupByAlbum()) {
      return [];
    }
    const groups: AlbumGroup[] = [];
    const seen = new Map<string, AlbumGroup>();
    let globalIndex = 0;
    for (const song of resolvedSongs.value) {
      const key = `${song.artist}|||${song.album}`;
      if (!seen.has(key)) {
        const g: AlbumGroup = {
          key,
          artist: song.artist,
          album: song.album,
          coverId: song.coverId,
          year: song.year,
          songs: [],
          startIndex: globalIndex,
        };
        seen.set(key, g);
        groups.push(g);
      }
      seen.get(key)!.songs.push(song);
      globalIndex++;
    }
    return groups;
  });

  function formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function trackLabel(song: Song): string {
    if (albumContext()) {
      return song.trackNumber > 0 ? String(song.trackNumber) : '—';
    }
    if (song.trackTotal > 0) {
      return `${song.trackNumber}/${song.trackTotal}`;
    }
    return song.trackNumber > 0 ? String(song.trackNumber) : '—';
  }

  function onMobileSortChange(e: Event) {
    const col = (e.target as HTMLSelectElement).value as SortCol;
    if (sortCol.value !== col) {
      sortDir.value = 1;
      albumSortMode.value = 'album';
    }
    sortCol.value = col;
    resetScroll();
  }

  function toggleSortDir() {
    sortDir.value = sortDir.value === 1 ? -1 : 1;
  }

  return {
    sortCol,
    sortDir,
    albumSortMode,
    sortedSongs,
    resolvedSongs,
    albumGroups,
    cycleSort,
    sortIndicator,
    albumColLabel,
    formatDuration,
    trackLabel,
    onMobileSortChange,
    toggleSortDir,
  };
}

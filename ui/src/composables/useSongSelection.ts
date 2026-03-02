import { ref, computed } from 'vue';
import type { Song } from '@/types/music';

export function useSongSelection(
  sortedSongs: () => Song[],
  _playlistMode: () => boolean
) {
  const selectedIds = ref<Set<number>>(new Set());
  const lastClickedIndex = ref<number>(-1);

  // 0 = none, 1 = some, 2 = all
  const selectionState = computed<0 | 1 | 2>(() => {
    const count = selectedIds.value.size;
    if (count === 0) {
      return 0;
    }
    if (count >= sortedSongs().length) {
      return 2;
    }
    return 1;
  });

  const selectedCount = computed(() => selectedIds.value.size);
  const multiIds = computed(() => [...selectedIds.value]);

  function isSelected(id: number): boolean {
    return selectedIds.value.has(id);
  }

  function clearSelection() {
    selectedIds.value = new Set();
  }

  function rangeSelect(fromIndex: number, toIndex: number) {
    const start = Math.min(fromIndex, toIndex);
    const end = Math.max(fromIndex, toIndex);
    for (let i = start; i <= end; i++) {
      selectedIds.value.add(sortedSongs()[i].id);
    }
  }

  // Clicking the checkbox TD (or the checkbox inside it)
  function handleCheckTd(index: number, event: MouseEvent) {
    event.stopPropagation();
    const song = sortedSongs()[index];
    if (event.shiftKey && lastClickedIndex.value >= 0) {
      event.preventDefault();
      rangeSelect(lastClickedIndex.value, index);
      lastClickedIndex.value = index;
    } else {
      // Toggle
      if (selectedIds.value.has(song.id)) {
        selectedIds.value.delete(song.id);
      } else {
        selectedIds.value.add(song.id);
      }
      lastClickedIndex.value = index;
    }
  }

  function selectSong(index: number, event: MouseEvent) {
    const song = sortedSongs()[index];
    if (event.shiftKey && lastClickedIndex.value >= 0) {
      event.preventDefault();
      rangeSelect(lastClickedIndex.value, index);
    } else if (event.metaKey || event.ctrlKey) {
      if (selectedIds.value.has(song.id)) {
        selectedIds.value.delete(song.id);
      } else {
        selectedIds.value.add(song.id);
      }
      lastClickedIndex.value = index;
    } else {
      selectedIds.value = new Set([song.id]);
      lastClickedIndex.value = index;
    }
  }

  function selectAlbumGroup(
    albumSongs: Song[],
    index: number,
    event: MouseEvent
  ) {
    if (event.shiftKey || event.metaKey || event.ctrlKey) {
      for (const s of albumSongs) {
        selectedIds.value.add(s.id);
      }
    } else {
      selectedIds.value = new Set(albumSongs.map((s) => s.id));
      lastClickedIndex.value = index;
    }
  }

  function handleRowClick(index: number, event: MouseEvent) {
    selectSong(index, event);
  }

  function handleAlbumGroupClick(
    albumSongs: Song[],
    index: number,
    event: MouseEvent
  ) {
    selectAlbumGroup(albumSongs, index, event);
  }

  function toggleSelectAll() {
    if (selectionState.value === 0) {
      selectedIds.value = new Set(sortedSongs().map((s) => s.id));
    } else {
      selectedIds.value = new Set();
    }
  }

  return {
    selectedIds,
    selectionState,
    selectedCount,
    multiIds,
    isSelected,
    clearSelection,
    toggleSelectAll,
    handleCheckTd,
    handleRowClick,
    handleAlbumGroupClick,
  };
}

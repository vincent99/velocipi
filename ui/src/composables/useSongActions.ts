import { ref, type ComputedRef } from 'vue';
import { useAdmin } from '@/composables/useAdmin';
import type { Song } from '@/types/music';

export interface SongTableEmit {
  enqueue(ids: number[]): void;
  append(ids: number[]): void;
  replace(ids: number[]): void;
  mark(ids: number[], marked: boolean): void;
  favorite(ids: number[], fav: boolean): void;
  delete(ids: number[]): void;
  edit(ids: number[]): void;
  removeFromPlaylist(ids: number[]): void;
}

export interface RowMenuState {
  songId: number;
}

export function useSongActions(
  emit: SongTableEmit,
  songs: () => Song[],
  multiIds: ComputedRef<number[]>,
  clearSelection: () => void
) {
  const { isAdmin } = useAdmin();

  const rowMenu = ref<RowMenuState | null>(null);

  function openRowMenu(songId: number, event: MouseEvent) {
    event.stopPropagation();
    if (rowMenu.value?.songId === songId) {
      rowMenu.value = null;
    } else {
      rowMenu.value = { songId };
    }
  }

  function closeRowMenu() {
    rowMenu.value = null;
  }

  function handleFlagChange(
    songId: number,
    field: 'marked' | 'favorite',
    value: boolean
  ) {
    if (field === 'marked') {
      emit.mark([songId], value);
    } else {
      emit.favorite([songId], value);
    }
  }

  // --- Row menu action wrappers ---

  function rowMenuEnqueue(songId: number) {
    emit.enqueue([songId]);
    closeRowMenu();
  }

  function rowMenuAppend(songId: number) {
    emit.append([songId]);
    closeRowMenu();
  }

  function rowMenuReplace(songId: number) {
    emit.replace([songId]);
    closeRowMenu();
  }

  function rowMenuMark(songId: number, marked: boolean) {
    emit.mark([songId], marked);
    closeRowMenu();
  }

  function rowMenuFavorite(songId: number, fav: boolean) {
    emit.favorite([songId], fav);
    closeRowMenu();
  }

  function rowMenuEdit(songId: number) {
    emit.edit([songId]);
    closeRowMenu();
  }

  function rowMenuDelete(songId: number) {
    const title = songs().find((s) => s.id === songId)?.title ?? 'this song';
    if (!confirm(`Permanently delete "${title}"? This cannot be undone.`)) {
      return;
    }
    emit.delete([songId]);
    closeRowMenu();
  }

  function rowMenuRemoveFromPlaylist(songId: number) {
    emit.removeFromPlaylist([songId]);
    closeRowMenu();
  }

  // --- Multi-select action wrappers ---

  function multiEnqueue() {
    emit.enqueue(multiIds.value);
  }

  function multiAppend() {
    emit.append(multiIds.value);
  }

  function multiReplace() {
    emit.replace(multiIds.value);
  }

  function multiMark(marked: boolean) {
    emit.mark(multiIds.value, marked);
  }

  function multiFavorite(fav: boolean) {
    emit.favorite(multiIds.value, fav);
  }

  function multiEdit() {
    emit.edit(multiIds.value);
  }

  function multiDelete() {
    const n = multiIds.value.length;
    const msg =
      n === 1
        ? `Permanently delete 1 song? This cannot be undone.`
        : `Permanently delete ${n} songs? This cannot be undone.`;
    if (!confirm(msg)) {
      return;
    }
    emit.delete(multiIds.value);
    clearSelection();
  }

  function multiRemoveFromPlaylist() {
    emit.removeFromPlaylist(multiIds.value);
    clearSelection();
  }

  return {
    isAdmin,
    rowMenu,
    openRowMenu,
    closeRowMenu,
    handleFlagChange,
    rowMenuEnqueue,
    rowMenuAppend,
    rowMenuReplace,
    rowMenuMark,
    rowMenuFavorite,
    rowMenuEdit,
    rowMenuDelete,
    rowMenuRemoveFromPlaylist,
    multiEnqueue,
    multiAppend,
    multiReplace,
    multiMark,
    multiFavorite,
    multiEdit,
    multiDelete,
    multiRemoveFromPlaylist,
  };
}

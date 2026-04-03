<script setup lang="ts">
import type { Song } from '@/types/music';
import ContextMenu from '@/components/remote/music/ContextMenu.vue';
import QueueActionButton from '@/components/remote/music/QueueActionButton.vue';

interface Props {
  song: Song;
  isAdmin: boolean;
  playlistMode: boolean;
  showFavorite?: boolean;
  showGoToArtist?: boolean;
  showGoToAlbum?: boolean;
  x: number;
  y: number;
}

withDefaults(defineProps<Props>(), {
  showFavorite: true,
  showGoToArtist: true,
  showGoToAlbum: true,
});

const emit = defineEmits<{
  close: [];
  mark: [value: boolean];
  favorite: [value: boolean];
  edit: [];
  delete: [];
  'remove-from-playlist': [];
  'go-to-artist': [];
  'go-to-album': [];
}>();
</script>

<template>
  <ContextMenu :x="x" :y="y" @close="emit('close')">
    <QueueActionButton
      :ids="[song.id]"
      variant="menu"
      @execute="emit('close')"
    />
    <template
      v-if="(song.artist && showGoToArtist) || (song.album && showGoToAlbum)"
    >
      <hr />
      <button
        v-if="song.artist && showGoToArtist"
        @click="
          emit('go-to-artist');
          emit('close');
        "
      >
        Go to Artist
      </button>
      <button
        v-if="song.album && showGoToAlbum"
        @click="
          emit('go-to-album');
          emit('close');
        "
      >
        Go to Album
      </button>
    </template>
    <hr />
    <button
      @click="
        emit('mark', !song.marked);
        emit('close');
      "
    >
      {{ song.marked ? 'Unmark' : 'Mark' }}
    </button>
    <button
      v-if="showFavorite"
      @click="
        emit('favorite', !song.favorite);
        emit('close');
      "
    >
      {{ song.favorite ? 'Unfavorite' : 'Favorite' }}
    </button>
    <button
      @click="
        emit('edit');
        emit('close');
      "
    >
      Edit
    </button>
    <template v-if="playlistMode">
      <hr />
      <button
        @click="
          emit('remove-from-playlist');
          emit('close');
        "
      >
        Remove from Playlist
      </button>
    </template>
    <template v-else-if="isAdmin">
      <hr />
      <button
        class="menu-danger"
        @click="
          emit('delete');
          emit('close');
        "
      >
        Delete
      </button>
    </template>
  </ContextMenu>
</template>

<style scoped lang="scss">
button {
  display: block;
  width: 100%;
  background: none;
  border: none;
  color: #e0e0e0;
  padding: 0.4rem 0.75rem;
  text-align: left;
  font-size: 0.85rem;
  cursor: pointer;

  &:hover {
    background: #3b82f6;
    color: #fff;
  }

  &.menu-danger {
    color: #f87171;

    &:hover {
      background: #7f1d1d;
      color: #fca5a5;
    }
  }
}

hr {
  border: none;
  border-top: 1px solid #444;
  margin: 0.25rem 0;
}
</style>

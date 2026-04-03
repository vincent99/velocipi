<script setup lang="ts">
import { ref, watch } from 'vue';
import type { Song } from '@/types/music';
import QueueActionButton from '@/components/remote/music/QueueActionButton.vue';

interface Props {
  song: Song;
  isOpen: boolean;
  isAdmin: boolean;
  playlistMode: boolean;
  // When false (grouped album view), the Favorite action is omitted
  showFavorite?: boolean;
  showGoToArtist?: boolean;
  showGoToAlbum?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  showFavorite: true,
  showGoToArtist: true,
  showGoToAlbum: true,
});

const emit = defineEmits<{
  open: [event: MouseEvent];
  mark: [value: boolean];
  favorite: [value: boolean];
  edit: [];
  delete: [];
  'remove-from-playlist': [];
  'go-to-artist': [];
  'go-to-album': [];
}>();

const triggerBtn = ref<HTMLButtonElement | null>(null);
const above = ref(false);

// Compute "above" when the menu opens so the dropdown doesn't overflow the viewport
watch(
  () => props.isOpen,
  (val) => {
    if (val && triggerBtn.value) {
      const rect = triggerBtn.value.getBoundingClientRect();
      above.value = window.innerHeight - rect.bottom < 130;
    }
  }
);

function handleOpen(event: MouseEvent) {
  emit('open', event);
}
</script>

<template>
  <div class="row-action-wrap">
    <button
      ref="triggerBtn"
      class="row-action-btn"
      title="Actions"
      @click.stop="handleOpen($event)"
    >
      …
    </button>
    <div v-if="isOpen" class="row-menu" :class="{ above }" @click.stop>
      <QueueActionButton :ids="[song.id]" variant="menu" />
      <template
        v-if="(song.artist && showGoToArtist) || (song.album && showGoToAlbum)"
      >
        <hr />
        <button
          v-if="song.artist && showGoToArtist"
          @click="emit('go-to-artist')"
        >
          Go to Artist
        </button>
        <button v-if="song.album && showGoToAlbum" @click="emit('go-to-album')">
          Go to Album
        </button>
      </template>
      <hr />
      <button @click="emit('mark', !song.marked)">
        {{ song.marked ? 'Unmark' : 'Mark' }}
      </button>
      <button v-if="showFavorite" @click="emit('favorite', !song.favorite)">
        {{ song.favorite ? 'Unfavorite' : 'Favorite' }}
      </button>
      <button @click="emit('edit')">Edit</button>
      <template v-if="playlistMode">
        <hr />
        <button @click="emit('remove-from-playlist')">
          Remove from Playlist
        </button>
      </template>
      <template v-else-if="isAdmin">
        <hr />
        <button class="menu-danger" @click="emit('delete')">Delete</button>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.row-action-wrap {
  position: relative;
  display: inline-block;
}

.row-action-btn {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 1rem;
  line-height: 1;
  // Visibility is controlled by parent row hover via :deep(.row-action-btn)
  opacity: 0;

  &:hover {
    background: #333;
    color: #ccc !important;
  }
}

.row-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 2px);
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.25rem 0;
  z-index: 500;
  min-width: 150px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
  white-space: nowrap;

  &.above {
    top: auto;
    bottom: calc(100% + 2px);
  }

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
}
</style>

<script setup lang="ts">
import { computed } from 'vue';
import { useSongStore } from '@/composables/useSongStore';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import type { Song } from '@/types/music';

const props = defineProps<{
  song: Song;
  // 'row': ghost when inactive, revealed on hover/touch-active (default)
  // 'header': always visible, dimmed when inactive
  variant?: 'row' | 'header';
}>();

const emit = defineEmits<{
  change: [field: 'marked' | 'favorite', value: boolean];
}>();

const { resolve } = useSongStore();
const { markSong, favoriteSong } = useMusicPlayer();

const resolved = computed(() => resolve(props.song));
const isMarked = computed(() => resolved.value.marked);
const isFavorite = computed(() => resolved.value.favorite);

const variant = computed(() => props.variant ?? 'row');

async function toggleFavorite(e: Event) {
  e.stopPropagation();
  const next = !isFavorite.value;
  await favoriteSong(props.song.id, next);
  emit('change', 'favorite', next);
}

async function toggleMark(e: Event) {
  e.stopPropagation();
  const next = !isMarked.value;
  await markSong(props.song.id, next);
  emit('change', 'marked', next);
}
</script>

<template>
  <button
    class="flag-btn"
    :class="[`flag-btn--${variant}`, { active: isFavorite }]"
    title="Favorite"
    @click="toggleFavorite"
  >
    ⭐
  </button>
  <button
    class="flag-btn"
    :class="[`flag-btn--${variant}`, { active: isMarked }]"
    title="Mark"
    @click="toggleMark"
  >
    🚩
  </button>
</template>

<style scoped lang="scss">
.flag-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  padding: 0 2px;
  margin-left: 2px;
  font-size: 0.72em;
  line-height: 1;
  cursor: pointer;
  transition: opacity 0.1s;

  // Row variant: ghost (hidden) when inactive, revealed by parent hover/touch-active
  &--row {
    opacity: 0;
    filter: grayscale(1);

    &.active {
      opacity: 1;
      filter: none;
    }
  }

  // Header variant: always visible, dimmed when inactive
  &--header {
    opacity: 0.25;

    &.active {
      opacity: 1;
    }
  }

  &:hover {
    opacity: 0.8 !important;
    filter: none !important;
  }
}
</style>

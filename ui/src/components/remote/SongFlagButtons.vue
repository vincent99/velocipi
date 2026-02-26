<script setup lang="ts">
import { computed } from 'vue';
import { useSongFlags } from '@/composables/useSongFlags';
import { useMusicPlayer } from '@/composables/useMusicPlayer';

const props = defineProps<{
  songId: number;
  // fallback values from the Song object (used before any override is set)
  markedFallback: boolean;
  favoriteFallback: boolean;
  // 'row': ghost when inactive, revealed on hover/touch-active (default)
  // 'header': always visible, dimmed when inactive
  variant?: 'row' | 'header';
}>();

const emit = defineEmits<{
  change: [field: 'marked' | 'favorite', value: boolean];
}>();

const { getMarked, getFavorite } = useSongFlags();
const { markSong, favoriteSong } = useMusicPlayer();

const isMarked = computed(() => getMarked(props.songId, props.markedFallback));
const isFavorite = computed(() =>
  getFavorite(props.songId, props.favoriteFallback)
);

const variant = computed(() => props.variant ?? 'row');

async function toggleFavorite(e: Event) {
  e.stopPropagation();
  const next = !isFavorite.value;
  await favoriteSong(props.songId, next);
  emit('change', 'favorite', next);
}

async function toggleMark(e: Event) {
  e.stopPropagation();
  const next = !isMarked.value;
  await markSong(props.songId, next);
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
  padding: 0;
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

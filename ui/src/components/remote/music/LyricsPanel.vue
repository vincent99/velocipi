<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { useLyrics } from '@/composables/useLyrics';

const { currentLines, currentIndex, hasLyrics, loading, isPlaying } =
  useLyrics();

const container = ref<HTMLElement | null>(null);

// Scroll active line into view, but only while playing.
// When paused the position stays frozen; when play resumes and the
// index advances the scroll picks up naturally.
watch(currentIndex, async (idx) => {
  if (idx < 0 || !container.value || !isPlaying.value) {
    return;
  }
  await nextTick();
  const el = container.value.children[idx] as HTMLElement | undefined;
  el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
});
</script>

<template>
  <div class="lyrics-panel">
    <div v-if="loading" class="lyrics-empty">Loading…</div>
    <div v-else-if="!hasLyrics" class="lyrics-empty">No lyrics</div>
    <div v-else ref="container" class="lyrics-lines">
      <div
        v-for="(line, idx) in currentLines"
        :key="idx"
        class="lyric-line"
        :class="{
          active: idx === currentIndex,
          paused: idx === currentIndex && !isPlaying,
        }"
      >
        {{ line.text || '\u00a0' }}
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.lyrics-panel {
  flex: 1;
  overflow-y: auto;
  padding: 0.25rem 0;
  min-height: 0;
}

.lyrics-empty {
  color: #555;
  font-size: 0.8rem;
  text-align: center;
  padding: 1.5rem 0;
}

.lyrics-lines {
  display: flex;
  flex-direction: column;
}

.lyric-line {
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
  color: #555;
  line-height: 1.5;
  border-radius: 3px;
  transition:
    color 0.25s,
    background 0.25s,
    font-weight 0.25s;

  &.active {
    color: #e0e0e0;
    font-weight: 600;
    background: rgba(59, 130, 246, 0.12);
  }

  &.active.paused {
    color: #aaa;
    background: rgba(59, 130, 246, 0.06);
  }
}
</style>

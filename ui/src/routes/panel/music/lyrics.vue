<script setup lang="ts">
import { computed } from 'vue';
import { useLyrics } from '@/composables/useLyrics';

const { currentLines, currentIndex, hasLyrics, loading, isPlaying } =
  useLyrics();

// Window starting 1 before the active line.
// Provide 6 lines so that context after a wrapped active line is never empty.
const displayLines = computed(() => {
  const ci = currentIndex.value;
  const all = currentLines.value;
  if (!all.length) {
    return [];
  }
  const start = Math.max(0, ci > 0 ? ci - 1 : 0);
  return all.slice(start, start + 6).map((l, i) => ({
    text: l.text,
    active: start + i === ci,
  }));
});
</script>

<template>
  <div class="lyrics-page">
    <div v-if="loading" class="no-lyrics">Loading…</div>
    <div v-else-if="!hasLyrics" class="no-lyrics">No lyrics</div>
    <template v-else>
      <div
        v-for="(line, idx) in displayLines"
        :key="idx"
        class="lyric-line"
        :class="{ active: line.active, paused: line.active && !isPlaying }"
      >
        {{ line.text || '\u00a0' }}
      </div>
    </template>
  </div>
</template>

<style scoped>
.lyrics-page {
  width: var(--panel-w, 256px);
  height: var(--panel-h, 64px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  color: #fff;
  font-size: 11px;
  padding: 0 4px;
  box-sizing: border-box;
}

.no-lyrics {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #444;
  font-size: 10px;
}

.lyric-line {
  flex-shrink: 0;
  height: 16px;
  line-height: 16px;
  color: #555;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.3s;
}

.lyric-line.active {
  /* Allow the active line to wrap onto the space used by the next lines.
     Cap at 3 lines (48px) so at least one following line remains visible. */
  height: auto;
  max-height: 48px;
  white-space: normal;
  overflow: hidden;
  color: #fff;
  font-weight: bold;
  font-size: 12px;
}

.lyric-line.active.paused {
  color: #888;
}
</style>

<script setup lang="ts">
import { onMounted } from 'vue';
import { RouterLink } from 'vue-router';
import dayjs from 'dayjs';
import { useSessions } from '@/composables/useSessions';
import type { SessionManifest } from '@/types';

const { sessions, refresh } = useSessions();
onMounted(refresh);

function label(s: SessionManifest): string {
  return dayjs(s.start_time).format('MMM D, HH:mm');
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-head">
      <span>Sessions</span>
      <button class="icon-btn" title="Refresh" @click="refresh">⟳</button>
    </div>
    <ul class="session-list">
      <li v-for="s in sessions" :key="s.session_id">
        <RouterLink :to="`/session/${s.session_id}`" class="session-link">
          <span class="dot" :class="{ live: s.live }" />
          <span class="when">{{ label(s) }}</span>
          <span class="tail">{{ s.aircraft }}</span>
        </RouterLink>
      </li>
      <li v-if="!sessions.length" class="empty-hint">No sessions yet.</li>
    </ul>
  </aside>
</template>

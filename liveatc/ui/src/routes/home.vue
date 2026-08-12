<script setup lang="ts">
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useSessions } from '@/composables/useSessions';

// Landing page: pick the live session (or the most recent) and jump to it.
const router = useRouter();
const { sessions, refresh } = useSessions();

onMounted(async () => {
  await refresh();
  const target = sessions.value.find((s) => s.live) ?? sessions.value[0];
  if (target) router.replace(`/session/${target.session_id}`);
});
</script>

<template>
  <div class="placeholder">
    <p v-if="!sessions.length">No recorded sessions yet.</p>
    <p v-else>Opening latest session…</p>
  </div>
</template>

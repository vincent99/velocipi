<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
import type { TransmissionRecord } from '@/types';
import { useSessions } from '@/composables/useSessions';
import { useTranscriptFeed } from '@/composables/useTranscriptFeed';
import { useAudioPlayer } from '@/composables/useAudioPlayer';
import TranscriptRow from '@/components/TranscriptRow.vue';

const route = useRoute();
const { sessions, refresh } = useSessions();
const { onRecord } = useTranscriptFeed();
const { tryAutoplay } = useAudioPlayer();

const records = ref<TransmissionRecord[]>([]);
const loading = ref(false);
// ids of transmissions that just arrived live, briefly highlighted then faded.
const highlighted = ref(new Set<string>());
// ready gates live auto-play so backfilled records during the initial load don't
// trigger playback -- only transmissions that arrive after load do.
const ready = ref(false);

const sessionId = computed(() => String(route.params.id));
const isLive = computed(
  () =>
    sessions.value.find((s) => s.session_id === sessionId.value)?.live ?? false
);

// Newest transmission at the top. start_time is an ISO-8601 UTC string, so a
// lexicographic descending sort is chronological.
const sortedRecords = computed(() =>
  [...records.value].sort((a, b) => b.start_time.localeCompare(a.start_time))
);

async function load() {
  ready.value = false;
  loading.value = true;
  records.value = [];
  try {
    const r = await fetch(`/api/transcripts/session/${sessionId.value}`);
    records.value = (await r.json()) as TransmissionRecord[];
  } catch (err) {
    console.error('session: load failed', err);
  } finally {
    loading.value = false;
    ready.value = true;
  }
}

// Insert a new record or replace an edited one (matched by id), keeping only
// records for the session currently on screen. Returns true if it was new.
function upsert(rec: TransmissionRecord): boolean {
  if (rec.session_id !== sessionId.value) return false;
  const i = records.value.findIndex((x) => x.id === rec.id);
  if (i >= 0) {
    records.value[i] = rec;
    return false;
  }
  records.value.push(rec);
  return true;
}

// Records pushed over the websocket (new transmissions + edits). When a genuinely
// new transmission arrives in the live session and nothing else is playing,
// auto-play it once.
function onWsRecord(rec: TransmissionRecord) {
  const isNew = upsert(rec);
  if (isNew && ready.value) {
    // Flash the new row green, then let it fade back (see CSS animation).
    highlighted.value.add(rec.id);
    setTimeout(() => highlighted.value.delete(rec.id), 3200);
    if (isLive.value) tryAutoplay(rec.id, `/api/media/${rec.audio_file}`);
  }
}

let off: (() => void) | null = null;
onMounted(async () => {
  if (!sessions.value.length) await refresh();
  await load();
  off = onRecord(onWsRecord);
});
onUnmounted(() => off?.());
watch(sessionId, load);
</script>

<template>
  <div class="session-view">
    <div class="session-head">
      <span class="badge" :class="{ live: isLive }">{{
        isLive ? 'LIVE' : 'SESSION'
      }}</span>
      <code class="sid">{{ sessionId }}</code>
      <span class="count">{{ records.length }} transmissions</span>
    </div>

    <div v-if="loading" class="placeholder">Loading transmissions…</div>
    <div v-else-if="!records.length" class="placeholder">
      No transmissions in this session yet.
    </div>
    <div v-else class="rows">
      <TranscriptRow
        v-for="r in sortedRecords"
        :key="r.id"
        :record="r"
        :session-id="sessionId"
        :highlight="highlighted.has(r.id)"
        @updated="upsert"
      />
    </div>
  </div>
</template>

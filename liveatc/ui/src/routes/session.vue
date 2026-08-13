<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { TransmissionRecord } from '@/types';
import { useSessions } from '@/composables/useSessions';
import { useTranscriptFeed } from '@/composables/useTranscriptFeed';
import { useAudioPlayer } from '@/composables/useAudioPlayer';
import TranscriptRow from '@/components/TranscriptRow.vue';

const route = useRoute();
const router = useRouter();
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

// Each record is in exactly one state. Saving a correction also marks reviewed,
// so "edited" wins over "correct".
type State = 'correct' | 'edited' | 'unreviewed';
function stateOf(r: TransmissionRecord): State {
  if (r.correction) return 'edited';
  if (r.reviewed) return 'correct';
  return 'unreviewed';
}

// Review breakdown; buckets are mutually exclusive and sum to the total.
const counts = computed(() => {
  let correct = 0;
  let edited = 0;
  let unreviewed = 0;
  for (const r of records.value) {
    const s = stateOf(r);
    if (s === 'edited') edited++;
    else if (s === 'correct') correct++;
    else unreviewed++;
  }
  return { total: records.value.length, correct, edited, unreviewed };
});

// Active filter, persisted in the URL (?filter=) so it survives reload.
const filter = computed<'all' | State>(() => {
  const f = route.query.filter;
  const v = Array.isArray(f) ? f[0] : f;
  return v === 'correct' || v === 'edited' || v === 'unreviewed' ? v : 'all';
});
function setFilter(f: 'all' | State) {
  router.replace({
    query: { ...route.query, filter: f === 'all' ? undefined : f },
  });
}

const visibleRecords = computed(() =>
  filter.value === 'all'
    ? sortedRecords.value
    : sortedRecords.value.filter((r) => stateOf(r) === filter.value)
);

// The single newest record has no later transmission to merge into.
const newestId = computed(() => sortedRecords.value[0]?.id ?? '');

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

function onDeleted(id: string) {
  records.value = records.value.filter((r) => r.id !== id);
}

// Merge result: the earlier record now holds the combined data; the later one
// (deletedId) is gone.
function onMerged(p: { merged: TransmissionRecord; deletedId: string }) {
  records.value = records.value.filter((r) => r.id !== p.deletedId);
  upsert(p.merged);
}

async function deleteSession() {
  if (
    !confirm(
      'Delete this entire session and all its recordings? This cannot be undone.'
    )
  ) {
    return;
  }
  try {
    const r = await fetch(`/api/transcripts/session/${sessionId.value}`, {
      method: 'DELETE',
    });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    await refresh();
    router.push('/');
  } catch (e) {
    alert('Delete failed: ' + (e instanceof Error ? e.message : String(e)));
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
      <span class="count">
        <button
          class="count-btn"
          :class="{ active: filter === 'all' }"
          @click="setFilter('all')"
        >
          {{ counts.total }} transmissions</button
        >,
        <button
          class="count-btn"
          :class="{ active: filter === 'correct' }"
          @click="setFilter('correct')"
        >
          {{ counts.correct }} correct</button
        >,
        <button
          class="count-btn"
          :class="{ active: filter === 'edited' }"
          @click="setFilter('edited')"
        >
          {{ counts.edited }} edited</button
        >,
        <button
          class="count-btn"
          :class="{ active: filter === 'unreviewed' }"
          @click="setFilter('unreviewed')"
        >
          {{ counts.unreviewed }} unreviewed
        </button>
      </span>
      <button
        v-if="!isLive"
        class="btn danger"
        title="Delete this entire session"
        @click="deleteSession"
      >
        Delete session
      </button>
    </div>

    <div v-if="loading" class="placeholder">Loading transmissions…</div>
    <div v-else-if="!records.length" class="placeholder">
      No transmissions in this session yet.
    </div>
    <div v-else-if="!visibleRecords.length" class="placeholder">
      No transmissions match this filter.
    </div>
    <div v-else class="rows">
      <TranscriptRow
        v-for="r in visibleRecords"
        :key="r.id"
        :record="r"
        :session-id="sessionId"
        :highlight="highlighted.has(r.id)"
        :can-merge="r.id !== newestId"
        @updated="upsert"
        @deleted="onDeleted"
        @merged="onMerged"
      />
    </div>
  </div>
</template>

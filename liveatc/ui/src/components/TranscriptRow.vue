<script setup lang="ts">
import { ref, computed } from 'vue';
import type { GPSFix, TransmissionRecord } from '@/types';
import { useAudioPlayer } from '@/composables/useAudioPlayer';

const props = defineProps<{
  record: TransmissionRecord;
  sessionId: string;
  highlight?: boolean;
}>();
const emit = defineEmits<{ updated: [TransmissionRecord] }>();

const editing = ref(false);
const draft = ref('');
const saving = ref(false);
const marking = ref(false);
const error = ref('');

const { currentId, play } = useAudioPlayer();
const playing = computed(() => currentId.value === props.record.id);

const audioURL = computed(() => `/api/media/${props.record.audio_file}`);

// Transmission start in UTC, e.g. "14:30:22Z".
const time = computed(
  () => new Date(props.record.start_time).toISOString().substr(11, 8) + 'Z'
);
const durationSec = computed(() =>
  (props.record.duration_ms / 1000).toFixed(1)
);
const confidencePct = computed(() =>
  Math.round((props.record.confidence || 0) * 100)
);

function gpsStr(f: GPSFix): string {
  if (!f?.valid) return 'no gps';
  const lat = `${f.lat >= 0 ? 'N' : 'S'}${Math.abs(f.lat).toFixed(2)}`;
  const lon = `${f.lon >= 0 ? 'E' : 'W'}${Math.abs(f.lon).toFixed(2)}`;
  return `${lat} ${lon} · ${Math.round(f.alt_ft)}ft · ${Math.round(f.groundspeed_kt)}kt`;
}

// Play the segment immediately, always from the start (rewind on each click).
function listen() {
  play(props.record.id, audioURL.value);
}

async function put(field: 'correction' | 'reviewed', payload: object) {
  error.value = '';
  const r = await fetch(
    `/api/transcripts/session/${props.sessionId}/${props.record.id}/${field}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  emit('updated', (await r.json()) as TransmissionRecord);
}

function startEdit() {
  draft.value = props.record.correction || props.record.transcript;
  error.value = '';
  editing.value = true;
}

async function saveCorrection() {
  saving.value = true;
  try {
    await put('correction', { correction: draft.value });
    editing.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

// Mark the machine transcript reviewed and error-free (no text change).
async function markReviewed() {
  marking.value = true;
  try {
    await put('reviewed', { reviewed: true });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    marking.value = false;
  }
}
</script>

<template>
  <div class="tx-row" :class="[record.direction, { flash: highlight }]">
    <div class="tx-meta">
      <span class="tx-time">{{ time }}</span>
      <span class="tx-dir" :class="record.direction">{{
        record.direction.toUpperCase()
      }}</span>
      <span class="tx-gps">{{ gpsStr(record.gps_start) }}</span>
      <span class="tx-dur">{{ durationSec }}s</span>
      <span class="tx-conf" :title="`whisper confidence`"
        >{{ confidencePct }}%</span
      >
      <span v-if="record.correction" class="tx-tag">corrected</span>
      <span v-if="record.reviewed" class="tx-tag reviewed">✓ reviewed</span>

      <span class="tx-actions">
        <span v-if="error && !editing" class="tx-error">{{ error }}</span>
        <button class="btn" :class="{ active: playing }" @click="listen">
          {{ playing ? 'Playing…' : 'Listen' }}
        </button>
        <button
          v-if="!record.reviewed && !editing"
          class="btn"
          :disabled="marking"
          title="Mark reviewed — transcript is correct as-is"
          @click="markReviewed"
        >
          {{ marking ? 'Marking…' : 'Correct' }}
        </button>
        <button class="btn" @click="editing ? (editing = false) : startEdit()">
          {{ editing ? 'Cancel' : 'Edit' }}
        </button>
      </span>
    </div>

    <div class="tx-body">
      <p class="tx-text" :class="{ superseded: record.correction }">
        {{ record.transcript || '(no transcript)' }}
      </p>
      <p v-if="record.correction" class="tx-correction">
        ✎ {{ record.correction }}
      </p>
    </div>

    <div v-if="editing" class="tx-editor">
      <textarea v-model="draft" rows="2" placeholder="Corrected transcript…" />
      <div class="tx-editor-actions">
        <button class="btn primary" :disabled="saving" @click="saveCorrection">
          {{ saving ? 'Saving…' : 'Save correction' }}
        </button>
        <span v-if="error" class="tx-error">{{ error }}</span>
      </div>
    </div>
  </div>
</template>

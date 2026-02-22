<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Recordings',
  icon: 'film-alt',
  sort: 5,
};
</script>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAdmin } from '@/composables/useAdmin';
import { useDeviceState } from '@/composables/useDeviceState';

interface RecordingFile {
  camera: string;
  date: string;
  startTime: string;
  filename: string;
  hasThumb: boolean;
  hasFull: boolean;
}

const route = useRoute();
const router = useRouter();
const { isAdmin } = useAdmin();
const { lastRecordingReady } = useDeviceState();

const recordings = ref<RecordingFile[]>([]);
const loading = ref(true);
const error = ref('');

onMounted(async () => {
  try {
    const r = await fetch('/recordings');
    if (!r.ok) {
      throw new Error(await r.text());
    }
    recordings.value = await r.json();
  } catch (e: unknown) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
});

watch(lastRecordingReady, (msg) => {
  if (!msg) {
    return;
  }
  // Add the new recording entry if not already present.
  const exists = recordings.value.some((r) => r.filename === msg.filename);
  if (!exists) {
    recordings.value.push({
      camera: msg.camera,
      date: msg.date,
      startTime: msg.filename.slice(11, 19), // "hh-mm-ss" from "yyyy-mm-dd_hh-mm-ss_cam"
      filename: msg.filename,
      hasThumb: true,
      hasFull: true,
    });
  }
});

// All unique dates sorted descending.
const dates = computed(() => {
  const set = new Set(recordings.value.map((r) => r.date));
  return [...set].sort((a, b) => b.localeCompare(a));
});

const selectedDate = computed(
  () => (route.query.date as string) || dates.value[0] || ''
);

function selectDate(d: string) {
  router.replace({ query: { date: d } });
}

// Recordings for the selected date.
const dayRecordings = computed(() =>
  recordings.value.filter((r) => r.date === selectedDate.value)
);

// Unique camera names for the selected date, sorted alphabetically.
const cameras = computed(() => {
  const set = new Set(dayRecordings.value.map((r) => r.camera));
  return [...set].sort((a, b) => a.localeCompare(b));
});

// Recordings grouped by camera.
const byCam = computed(() => {
  const map = new Map<string, RecordingFile[]>();
  for (const rec of dayRecordings.value) {
    const list = map.get(rec.camera) ?? [];
    list.push(rec);
    map.set(rec.camera, list);
  }
  return map;
});

// Hours that have at least one recording on the selected day.
const hours = computed(() => {
  const set = new Set(
    dayRecordings.value.map((r) => r.startTime.split('-')[0])
  );
  return [...set].sort();
});

// Parse a recording's UTC date+startTime into a Date object.
function recToUtcDate(date: string, startTime: string): Date {
  const [y, mo, d] = date.split('-').map(Number);
  const [h, m, s] = startTime.split('-').map(Number);
  return new Date(Date.UTC(y, mo - 1, d, h, m, s));
}

// Format "hh-mm-ss" UTC as "hh:mmZ" or "hh:mm:ssZ" (omit seconds when zero).
function formatUtc(t: string): string {
  const [h, m, s] = t.split('-');
  return s === '00' ? `${h}:${m}Z` : `${h}:${m}:${s}Z`;
}

// Format a Date as local HH:MM:SS.
function formatLocal(dt: Date): string {
  return dt.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

// Return local HH:MM for a UTC hour label (using the first minute of that hour).
function localHourLabel(date: string, utcHour: string): string {
  const dt = recToUtcDate(date, `${utcHour}-00-00`);
  return dt.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

// Day offset (+1, -1, 0) between local date and UTC date for a given recording.
function localDayOffset(date: string, startTime: string): number {
  const dt = recToUtcDate(date, startTime);
  const localDateStr = dt.toLocaleDateString('en-CA'); // YYYY-MM-DD
  if (localDateStr > date) {
    return 1;
  }
  if (localDateStr < date) {
    return -1;
  }
  return 0;
}

// For a given UTC date, the dominant local day offset (sign of the majority,
// or the first non-zero one found). Used to annotate the sidebar date label.
const dateDayOffset = computed(() => {
  const map = new Map<string, number>();
  for (const d of dates.value) {
    const recs = recordings.value.filter((r) => r.date === d);
    const offset =
      recs.length > 0 ? localDayOffset(recs[0].date, recs[0].startTime) : 0;
    map.set(d, offset);
  }
  return map;
});

// --- Delete actions ---

async function deleteRecording(rec: RecordingFile) {
  if (
    !confirm(
      `Delete recording ${formatLocal(recToUtcDate(rec.date, rec.startTime))}?`
    )
  ) {
    return;
  }
  try {
    const r = await fetch(`/recordings/${rec.date}/${rec.filename}`, {
      method: 'DELETE',
    });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    recordings.value = recordings.value.filter(
      (x) => x.filename !== rec.filename
    );
  } catch (e: unknown) {
    alert('Delete failed: ' + String(e));
  }
}

async function deleteHour(hour: string) {
  if (!selectedDate.value) {
    return;
  }
  if (
    !confirm(
      `Delete all recordings for ${localHourLabel(selectedDate.value, hour)} (${hour}:00Z)?`
    )
  ) {
    return;
  }
  try {
    const r = await fetch(`/recordings/hour/${selectedDate.value}/${hour}`, {
      method: 'DELETE',
    });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    recordings.value = recordings.value.filter(
      (x) => !(x.date === selectedDate.value && x.startTime.startsWith(hour))
    );
  } catch (e: unknown) {
    alert('Delete failed: ' + String(e));
  }
}

async function deleteDay() {
  const date = selectedDate.value;
  if (!date) {
    return;
  }
  if (!confirm(`Delete all recordings for ${date}?`)) {
    return;
  }
  try {
    const r = await fetch(`/recordings/day/${date}`, { method: 'DELETE' });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    recordings.value = recordings.value.filter((x) => x.date !== date);
    // Navigate to next available date.
    const next = dates.value.find((d) => d !== date);
    router.replace({ query: next ? { date: next } : {} });
  } catch (e: unknown) {
    alert('Delete failed: ' + String(e));
  }
}
</script>

<template>
  <div class="recordings-page">
    <div v-if="loading" class="status-msg">Loading…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>
    <div v-else-if="dates.length === 0" class="status-msg">
      No recordings found.
    </div>

    <div v-else class="layout">
      <!-- Sidebar: date list -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">Dates</span>
        </div>
        <ul class="date-list">
          <li
            v-for="d in dates"
            :key="d"
            class="date-item"
            :class="{ active: d === selectedDate }"
            @click="selectDate(d)"
          >
            {{ d
            }}<sup v-if="dateDayOffset.get(d)" class="day-offset">{{
              dateDayOffset.get(d)! > 0 ? '+1' : '−1'
            }}</sup>
          </li>
        </ul>
      </aside>

      <!-- Timeline body -->
      <main class="timeline-wrap">
        <div
          v-if="!selectedDate || dayRecordings.length === 0"
          class="status-msg"
        >
          No recordings for this date.
        </div>
        <div v-else class="timeline">
          <!-- Header row: camera names + optional delete-day button -->
          <div class="tl-header">
            <div class="tl-time-col"></div>
            <div
              v-for="cam in cameras"
              :key="cam"
              class="tl-cam-col tl-cam-header"
            >
              {{ cam }}
            </div>
            <div v-if="isAdmin" class="tl-actions-col">
              <button
                class="del-day-btn"
                title="Delete entire day"
                @click="deleteDay"
              >
                <i class="fi-sr-trash" /> Delete day
              </button>
            </div>
          </div>

          <!-- Per-hour rows -->
          <div v-for="hour in hours" :key="hour" class="tl-hour-row">
            <div class="tl-time-col tl-hour-label">
              <span class="tl-local-time">{{
                localHourLabel(selectedDate, hour)
              }}</span>
              <span class="tl-utc-time">({{ hour }}:00Z)</span>
            </div>
            <div v-for="cam in cameras" :key="cam" class="tl-cam-col tl-cell">
              <template
                v-for="rec in (byCam.get(cam) ?? []).filter((r) =>
                  r.startTime.startsWith(hour)
                )"
                :key="rec.filename"
              >
                <a
                  :href="`/recordings/${rec.date}/${rec.filename}.mp4`"
                  target="_blank"
                  class="thumb-link"
                >
                  <img
                    v-if="rec.hasThumb"
                    :src="`/recordings/${rec.date}/${rec.filename}_thumb.jpg`"
                    class="thumb-img"
                    :alt="rec.filename"
                  />
                  <div v-else class="thumb-placeholder">
                    <span>{{
                      formatLocal(recToUtcDate(rec.date, rec.startTime))
                    }}</span>
                    <span class="ph-utc">({{ formatUtc(rec.startTime) }})</span>
                  </div>
                  <button
                    v-if="isAdmin"
                    class="del-btn"
                    title="Delete recording"
                    @click.stop.prevent="deleteRecording(rec)"
                  >
                    <i class="fi-sr-trash" />
                  </button>
                </a>
              </template>
            </div>
            <div v-if="isAdmin" class="tl-actions-col">
              <button
                class="del-hour-btn"
                :title="`Delete ${hour}:00 recordings`"
                @click="deleteHour(hour)"
              >
                <i class="fi-sr-trash" />
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped lang="scss">
.recordings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  color: #e0e0e0;
  font-size: 0.875rem;
}

.status-msg {
  color: #888;
  padding: 2rem 1rem;
}

.error-msg {
  color: #f87171;
  padding: 1rem;
}

.layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

// Sidebar
.sidebar {
  width: 140px;
  flex-shrink: 0;
  border-right: 1px solid #333;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 0.75rem;
  color: #888;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.date-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  flex: 1;
}

.date-item {
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  font-size: 0.8rem;
  color: #ccc;

  &:hover {
    background: #2a2a2a;
  }

  &.active {
    background: #1e3a5f;
    color: #fff;
  }
}

// Timeline
.timeline-wrap {
  flex: 1;
  overflow: auto;
  padding: 0.5rem;
}

.timeline {
  min-width: 300px;
}

.tl-header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #333;
  padding-bottom: 0.4rem;
  margin-bottom: 0.25rem;
  position: sticky;
  top: 0;
  background: #111;
  z-index: 2;
}

.tl-hour-row {
  display: flex;
  align-items: flex-start;
  border-bottom: 1px solid #222;
  padding: 0.25rem 0;
}

.tl-time-col {
  width: 72px;
  flex-shrink: 0;
  font-size: 0.72rem;
  color: #666;
  padding-top: 0.2rem;
}

.tl-cam-col {
  flex: 1;
  min-width: 80px;
}

.tl-cam-header {
  font-size: 0.78rem;
  font-weight: 600;
  color: #bbb;
  padding: 0 0.25rem;
}

.tl-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 0 0.25rem;
}

.tl-actions-col {
  width: 80px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb-link {
  display: inline-block;
  position: relative;
  text-decoration: none;
}

.thumb-img {
  display: block;
  height: 60px;
  width: auto;
  border-radius: 3px;
  border: 1px solid #444;
}

.thumb-placeholder {
  height: 60px;
  width: 107px;
  border: 1px solid #444;
  border-radius: 3px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.1rem;
  font-size: 0.7rem;
  color: #ccc;
  background: #1a1a1a;
}

.del-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  background: rgba(0, 0, 0, 0.7);
  border: none;
  border-radius: 3px;
  color: #f87171;
  cursor: pointer;
  font-size: 0.7rem;
  padding: 2px 4px;
  line-height: 1;
  opacity: 0;
  transition: opacity 0.1s;

  .thumb-link:hover & {
    opacity: 1;
  }

  &:hover {
    background: #7f1d1d;
    color: #fff;
  }
}

.del-hour-btn {
  background: none;
  border: 1px solid #ef4444;
  border-radius: 4px;
  color: #ef4444;
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0.2rem 0.4rem;

  &:hover {
    background: #7f1d1d;
    color: #fff;
  }
}

.del-day-btn {
  background: none;
  border: 1px solid #ef4444;
  border-radius: 4px;
  color: #ef4444;
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  white-space: nowrap;

  &:hover {
    background: #7f1d1d;
    color: #fff;
  }
}

.tl-hour-label {
  padding-top: 0.3rem;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.tl-local-time {
  font-size: 0.72rem;
  color: #ccc;
}

.tl-utc-time {
  font-size: 0.62rem;
  color: #555;
}

.day-offset {
  font-size: 0.6rem;
  color: #facc15;
  vertical-align: super;
  margin-left: 1px;
}

.ph-utc {
  display: block;
  font-size: 0.6rem;
  color: #555;
}
</style>

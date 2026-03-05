<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Recordings',
  icon: 'film',
  iconStyle: 'rr',
  sort: 5,
};
</script>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAdmin } from '@/composables/useAdmin';
import { useDeviceState } from '@/composables/useDeviceState';
import type { DVRRecordingState } from '@/types/ws';

interface RecordingFile {
  camera: string;
  session: string;
  date: string;
  startTime: string;
  filename: string;
  hasThumb: boolean;
  hasFull: boolean;
}

const route = useRoute();
const router = useRouter();
const { isAdmin } = useAdmin();
const { lastRecordingReady, dvrState, diskSpace } = useDeviceState();

const recordings = ref<RecordingFile[]>([]);
const loading = ref(true);
const error = ref('');
const togglingState = ref(false);

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
      session: msg.session,
      date: msg.filename.slice(0, 10), // "yyyy-mm-dd" from "yyyy-mm-dd_hh-mm-ss_cam"
      startTime: msg.filename.slice(11, 19), // "hh-mm-ss"
      filename: msg.filename,
      hasThumb: true,
      hasFull: true,
    });
  }
});

// All unique sessions sorted descending.
const sessions = computed(() => {
  const set = new Set(recordings.value.map((r) => r.session));
  return [...set].sort((a, b) => b.localeCompare(a));
});

const selectedSession = computed(
  () => (route.query.session as string) || sessions.value[0] || ''
);

function selectSession(s: string) {
  router.replace({ query: { session: s } });
}

// Recordings for the selected session.
const sessionRecordings = computed(() =>
  recordings.value.filter((r) => r.session === selectedSession.value)
);

// Unique camera names for the selected session, sorted alphabetically.
const cameras = computed(() => {
  const set = new Set(sessionRecordings.value.map((r) => r.camera));
  return [...set].sort((a, b) => a.localeCompare(b));
});

// Recordings grouped by camera.
const byCam = computed(() => {
  const map = new Map<string, RecordingFile[]>();
  for (const rec of sessionRecordings.value) {
    const list = map.get(rec.camera) ?? [];
    list.push(rec);
    map.set(rec.camera, list);
  }
  return map;
});

// Hours that have at least one recording in the selected session, sorted descending.
const hours = computed(() => {
  const set = new Set(
    sessionRecordings.value.map((r) => r.startTime.split('-')[0])
  );
  return [...set].sort((a, b) => b.localeCompare(a));
});

// Parse a recording's UTC date+startTime into a Date object.
function recToUtcDate(date: string, startTime: string): Date {
  const [y = 0, mo = 1, d = 1] = date.split('-').map(Number);
  const [h = 0, m = 0, s = 0] = startTime.split('-').map(Number);
  return new Date(Date.UTC(y, mo - 1, d, h, m, s));
}

// Format "hh-mm-ss" UTC as "hh:mmZ" or "hh:mm:ssZ" (omit seconds when zero).
function formatUtc(t: string): string {
  const [h, m, s] = t.split('-');
  return s === '00' ? `${h}:${m}Z` : `${h}:${m}:${s}Z`;
}

// Format a Date as local time in 12-hour format (e.g. "10:09:48pm").
function formatLocal(dt: Date): string {
  return dt
    .toLocaleTimeString([], {
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    })
    .toLowerCase();
}

// Return local hour label for a UTC date+hour (using the first minute of that hour).
// Format: "10pm" or "10:30pm" if minutes are non-zero.
function localHourLabel(date: string, utcHour: string): string {
  const dt = recToUtcDate(date, `${utcHour}-00-00`);
  return dt
    .toLocaleTimeString([], {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    })
    .toLowerCase()
    .replace(':00', '');
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

// For an hour row we need a representative date. Pick the date from the first
// recording in this session that falls in this hour.
function dateForHour(hour: string): string {
  const rec = sessionRecordings.value.find((r) =>
    r.startTime.startsWith(hour ?? '')
  );
  return rec?.date ?? selectedSession.value.slice(0, 10);
}

// --- DVR state ---

async function toggleRecordingState() {
  if (!dvrState.value) {
    return;
  }
  const next: DVRRecordingState = dvrState.value === 'on' ? 'paused' : 'on';
  togglingState.value = true;
  try {
    await fetch('/dvr/state', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: next }),
    });
  } finally {
    togglingState.value = false;
  }
}

// Disk space display helpers.
const diskBar = computed(() => {
  if (!diskSpace.value) {
    return null;
  }
  return {
    pct: Math.round(diskSpace.value.usedPct),
    free: diskSpace.value.freeGB.toFixed(1),
    total: diskSpace.value.totalGB.toFixed(1),
    used: diskSpace.value.usedGB.toFixed(1),
  };
});

// --- Fullscreen playback ---

function playFullscreen(url: string) {
  const video = document.createElement('video');
  video.src = url;
  video.controls = true;
  video.style.cssText =
    'position:fixed;inset:0;width:100%;height:100%;background:#000;z-index:9999';
  document.body.appendChild(video);

  function cleanup() {
    video.pause();
    document.body.removeChild(video);
    document.removeEventListener('fullscreenchange', onFsChange);
  }

  function onFsChange() {
    if (!document.fullscreenElement) {
      cleanup();
    }
  }

  document.addEventListener('fullscreenchange', onFsChange);
  video
    .requestFullscreen()
    .then(() => video.play())
    .catch(cleanup);
}

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
    const r = await fetch(`/recordings/${rec.session}/${rec.filename}`, {
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
  if (!selectedSession.value) {
    return;
  }
  const date = dateForHour(hour);
  if (
    !confirm(
      `Delete all recordings for ${localHourLabel(date, hour)} (${hour}:00Z)?`
    )
  ) {
    return;
  }
  try {
    const r = await fetch(`/recordings/hour/${selectedSession.value}/${hour}`, {
      method: 'DELETE',
    });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    recordings.value = recordings.value.filter(
      (x) =>
        !(x.session === selectedSession.value && x.startTime.startsWith(hour))
    );
  } catch (e: unknown) {
    alert('Delete failed: ' + String(e));
  }
}

async function deleteSession() {
  const sess = selectedSession.value;
  if (!sess) {
    return;
  }
  if (!confirm(`Delete all recordings for session ${sess}?`)) {
    return;
  }
  try {
    const r = await fetch(`/recordings/session/${sess}`, { method: 'DELETE' });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    recordings.value = recordings.value.filter((x) => x.session !== sess);
    // Navigate to next available session.
    const next = sessions.value.find((s) => s !== sess);
    router.replace({ query: next ? { session: next } : {} });
  } catch (e: unknown) {
    alert('Delete failed: ' + String(e));
  }
}
</script>

<template>
  <div class="recordings-page">
    <!-- Status bar: disk usage + DVR state -->
    <div class="status-bar">
      <div v-if="diskBar" class="disk-info">
        <div class="disk-bar-wrap">
          <div
            class="disk-bar-fill"
            :style="{ width: diskBar.pct + '%' }"
            :class="{ warn: diskBar.pct >= 80, crit: diskBar.pct >= 95 }"
          />
        </div>
        <span class="disk-label">
          {{ diskBar.used }} of {{ diskBar.total }} GB used
        </span>
      </div>
      <div v-else class="disk-info warn disk-unknown">Disk: Unknown</div>

      <div class="dvr-state-wrap">
        <span
          class="dvr-state-dot"
          :class="dvrState ?? 'unknown'"
          :title="`DVR: ${dvrState ?? 'unknown'}`"
        />
        <span class="dvr-state-label">{{ dvrState ?? 'Unknown' }}</span>
        <button
          v-if="isAdmin && dvrState && dvrState !== 'off'"
          class="dvr-toggle-btn"
          :disabled="togglingState"
          @click="toggleRecordingState"
        >
          <i v-if="dvrState === 'on'" class="fi-sr-pause" />
          <i v-else class="fi-sr-play" />
          {{ dvrState === 'on' ? 'Pause' : 'Resume' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="status-msg">Loading…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>
    <div v-else-if="sessions.length === 0" class="status-msg">
      No recordings found.
    </div>

    <div v-else class="layout">
      <!-- Sidebar: session list -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">Sessions</span>
        </div>
        <ul class="session-list">
          <li
            v-for="s in sessions"
            :key="s"
            class="session-item"
            :class="{ active: s === selectedSession }"
            @click="selectSession(s)"
          >
            {{ s }}
          </li>
        </ul>
      </aside>

      <!-- Timeline body -->
      <main class="timeline-wrap">
        <div
          v-if="!selectedSession || sessionRecordings.length === 0"
          class="status-msg"
        >
          No recordings for this session.
        </div>
        <div v-else class="timeline">
          <!-- Header row: camera names + optional delete-session button -->
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
                class="del-session-btn"
                title="Delete entire session"
                @click="deleteSession"
              >
                <i class="fi-sr-trash" /> Delete session
              </button>
            </div>
          </div>

          <!-- Per-hour rows -->
          <div v-for="hour in hours" :key="hour" class="tl-hour-row">
            <div class="tl-time-col tl-hour-label">
              <span class="tl-local-time"
                >{{ localHourLabel(dateForHour(hour ?? ''), hour ?? '')
                }}<sup
                  v-if="
                    localDayOffset(
                      dateForHour(hour ?? ''),
                      `${hour ?? ''}-00-00`
                    )
                  "
                  class="day-offset"
                  >{{
                    localDayOffset(
                      dateForHour(hour ?? ''),
                      `${hour ?? ''}-00-00`
                    ) > 0
                      ? '+1'
                      : '−1'
                  }}</sup
                ></span
              >
              <span class="tl-utc-time">({{ hour }}:00Z)</span>
            </div>
            <div v-for="cam in cameras" :key="cam" class="tl-cam-col tl-cell">
              <template
                v-for="rec in (byCam.get(cam) ?? []).filter((r) =>
                  r.startTime.startsWith(hour ?? '')
                )"
                :key="rec.filename"
              >
                <a
                  :href="`/recordings/${rec.session}/${rec.filename}.mp4`"
                  target="_blank"
                  class="thumb-link"
                  @click.prevent="
                    playFullscreen(
                      `/recordings/${rec.session}/${rec.filename}.mp4`
                    )
                  "
                >
                  <img
                    v-if="rec.hasThumb"
                    :src="`/recordings/${rec.session}/${rec.filename}_thumb.jpg`"
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
                @click="deleteHour(hour ?? '')"
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

// Status bar
.status-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.4rem 0.75rem;
  border-bottom: 1px solid #333;
  background: #161616;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.disk-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: #aaa;
}

.disk-unknown {
  color: #555;
}

.disk-bar-wrap {
  width: 80px;
  height: 6px;
  background: #333;
  border-radius: 3px;
  overflow: hidden;
}

.disk-bar-fill {
  height: 100%;
  background: #3b82f6;
  border-radius: 3px;
  transition: width 0.4s;

  &.warn {
    background: #f59e0b;
  }

  &.crit {
    background: #ef4444;
  }
}

.disk-label {
  white-space: nowrap;
}

.dvr-state-wrap {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  margin-left: auto;
}

.dvr-state-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #555;
  flex-shrink: 0;

  &.on {
    background: #22c55e;
    box-shadow: 0 0 4px #22c55e80;
  }

  &.paused {
    background: #f59e0b;
  }

  &.off {
    background: #555;
  }
}

.dvr-state-label {
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 0.7rem;
}

.dvr-toggle-btn {
  background: none;
  border: 1px solid #555;
  border-radius: 4px;
  color: #ccc;
  cursor: pointer;
  font-size: 0.72rem;
  padding: 0.15rem 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;

  &:hover:not(:disabled) {
    border-color: #888;
    color: #fff;
  }

  &:disabled {
    opacity: 0.5;
    cursor: default;
  }
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

.session-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  flex: 1;
}

.session-item {
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
  width: 120px;
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

.del-session-btn {
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

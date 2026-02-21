<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Cameras',
  icon: 'camera-viewfinder',
};
</script>

<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue';
import Hls from 'hls.js';

const cameras = ref<string[]>([]);
const selected = ref<string>('');
const videoEl = ref<HTMLVideoElement | null>(null);
const error = ref('');
const snapshotSrc = ref('');

let hls: Hls | null = null;
let snapshotTimer: ReturnType<typeof setInterval> | null = null;

function snapshotUrl(name: string) {
  return `/snapshot/${encodeURIComponent(name)}?t=${Date.now()}`;
}

function startSnapshots(name: string) {
  stopSnapshots();
  snapshotSrc.value = snapshotUrl(name);
  snapshotTimer = setInterval(() => {
    snapshotSrc.value = snapshotUrl(name);
  }, 5000);
}

function stopSnapshots() {
  if (snapshotTimer !== null) {
    clearInterval(snapshotTimer);
    snapshotTimer = null;
  }
  snapshotSrc.value = '';
}

async function loadCameras() {
  try {
    const r = await fetch('/cameras');
    if (!r.ok) {
      throw new Error(await r.text());
    }
    const data: { name: string }[] = await r.json();
    cameras.value = data.map((c) => c.name);
    if (cameras.value.length > 0 && !selected.value) {
      selected.value = cameras.value[0] ?? '';
    }
  } catch (e) {
    error.value = 'Failed to load cameras: ' + String(e);
  }
}

function destroyHls() {
  if (hls) {
    hls.destroy();
    hls = null;
  }
}

function startStream(name: string) {
  destroyHls();
  if (!videoEl.value || !name) {
    return;
  }

  const src = `/hls/${encodeURIComponent(name)}/stream.m3u8`;
  const video = videoEl.value;

  if (Hls.isSupported()) {
    hls = new Hls({ lowLatencyMode: true });
    hls.loadSource(src);
    hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, (_evt, data) => {
      if (data.fatal) {
        error.value = 'Stream error: ' + data.type;
      }
    });
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    // Native HLS (Safari)
    video.src = src;
  } else {
    error.value = 'HLS is not supported in this browser.';
  }
}

watch(selected, async (name) => {
  error.value = '';
  await nextTick();
  startStream(name);
  startSnapshots(name);
});

onUnmounted(() => {
  destroyHls();
  stopSnapshots();
});

loadCameras();
</script>

<template>
  <div class="cameras-page">
    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-if="cameras.length === 0 && !error" class="empty">
      No cameras configured. Add cameras in Settings.
    </div>

    <div v-if="cameras.length > 0" class="controls">
      <label class="cam-label">Camera</label>
      <select v-model="selected" class="cam-select">
        <option v-for="name in cameras" :key="name" :value="name">
          {{ name }}
        </option>
      </select>
    </div>

    <div v-if="selected" class="video-wrap">
      <video ref="videoEl" class="video" autoplay muted playsinline controls />
    </div>

    <div v-if="snapshotSrc" class="snapshot-wrap">
      <div class="snapshot-label">Snapshot</div>
      <img :src="snapshotSrc" class="snapshot" alt="Camera snapshot" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.cameras-page {
  padding: 1.5rem 1rem;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 900px;
  margin: 0 auto;
}

.error-banner {
  background: #5a1a1a;
  border: 1px solid #a33;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  color: #f88;
}

.empty {
  color: #666;
  font-size: 0.9rem;
  padding: 2rem 0;
}

.controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.cam-label {
  font-size: 0.9rem;
  color: #aaa;
  white-space: nowrap;
}

.cam-select {
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.9rem;
  cursor: pointer;

  &:focus {
    outline: none;
    border-color: #666;
  }
}

.video-wrap {
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.video {
  width: 100%;
  display: block;
  max-height: 70vh;
}

.snapshot-wrap {
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.snapshot-label {
  font-size: 0.75rem;
  color: #666;
  padding: 0.4rem 0.6rem 0;
}

.snapshot {
  width: 100%;
  display: block;
}
</style>

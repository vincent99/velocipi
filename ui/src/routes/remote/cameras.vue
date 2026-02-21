<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Cameras',
  icon: 'camera-viewfinder',
};
</script>

<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import Hls from 'hls.js';

const route = useRoute();

const videoEl = ref<HTMLVideoElement | null>(null);
const error = ref('');

// Selected camera comes from the ?cam= query param.
const selected = ref((route.query.cam as string) ?? '');

watch(
  () => route.query.cam,
  (cam) => {
    selected.value = (cam as string) ?? '';
  }
);

let hls: Hls | null = null;

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
    video.src = src;
  } else {
    error.value = 'HLS is not supported in this browser.';
  }
}

watch(selected, async (name) => {
  error.value = '';
  await nextTick();
  startStream(name);
});

// Kick off the initial stream if the page loaded with a ?cam= param.
if (selected.value) {
  nextTick(() => startStream(selected.value));
}

onUnmounted(destroyHls);
</script>

<template>
  <div class="cameras-page">
    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-if="!selected" class="empty">
      Select a camera from the header to view a live stream.
    </div>

    <div v-if="selected" class="video-wrap">
      <video ref="videoEl" class="video" autoplay muted playsinline controls />
    </div>
  </div>
</template>

<style scoped lang="scss">
.cameras-page {
  // Counteract remote-main's 1rem padding so the video fills edge-to-edge.
  margin: -1rem;
  height: calc(100% + 2rem);
  display: flex;
  flex-direction: column;
  color: #e0e0e0;
}

.error-banner {
  background: #5a1a1a;
  border: 1px solid #a33;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  color: #f88;
  flex-shrink: 0;
}

.empty {
  color: #666;
  font-size: 0.9rem;
  padding: 2rem 1rem;
}

.video-wrap {
  flex: 1;
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0; // required for flex child to shrink below content size
}

.video {
  // Fill the wrap but never exceed it, preserving aspect ratio.
  max-width: 100%;
  max-height: 100%;
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
</style>

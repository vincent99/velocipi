<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Cameras',
  icon: 'camera-viewfinder',
};
</script>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Hls from 'hls.js';
import { useCameraList } from '@/composables/useCameraList';

const route = useRoute();
const router = useRouter();
const { cameras, cameraList } = useCameraList();

// Whether the currently selected camera has audio enabled.
const selectedAudio = computed(() => {
  const cam = cameraList.value.find((c) => c.name === selected.value);
  return cam?.audio ?? false;
});

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

// If no camera is selected, redirect to the first one once the list loads.
watch(
  cameras,
  (list) => {
    if (!selected.value && list.length > 0) {
      router.replace({ path: '/remote/cameras', query: { cam: list[0] } });
    }
  },
  { immediate: true }
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
  video.muted = !selectedAudio.value;

  if (Hls.isSupported()) {
    hls = new Hls({
      lowLatencyMode: true,
      // Always start at the live edge, not the beginning of the playlist window.
      liveSyncMode: 'edge',
      // Target 4s behind the live edge (2 × 2s segments). Using explicit
      // duration avoids multiplying by segment target duration which can vary.
      liveSyncDuration: 4,
      // Beyond 8s latency, skip segments to catch back up.
      liveMaxLatencyDuration: 8,
      // Allow up to 1.2× playback speed to drift back to the target when
      // the player falls behind without needing to hard-skip.
      maxLiveSyncPlaybackRate: 1.2,
      // Keep the forward buffer tight so we don't drift ahead of live.
      maxBufferLength: 6,
      maxMaxBufferLength: 10,
      // Don't keep a large back-buffer — we're watching live, not seeking.
      backBufferLength: 10,
    });
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
      <video ref="videoEl" class="video" autoplay playsinline controls />
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

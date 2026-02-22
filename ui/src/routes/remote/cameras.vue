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
import mpegts from 'mpegts.js';
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

let player: mpegts.Player | null = null;

function destroyPlayer() {
  if (player) {
    player.pause();
    player.unload();
    player.detachMediaElement();
    player.destroy();
    player = null;
  }
}

function startStream(name: string) {
  destroyPlayer();
  if (!videoEl.value || !name) {
    return;
  }

  const video = videoEl.value;
  video.muted = !selectedAudio.value;

  if (!mpegts.isSupported()) {
    error.value = 'MPEG-TS streaming is not supported in this browser.';
    return;
  }

  // Use an absolute URL — mpegts.js fetches inside a Web Worker where
  // relative URLs have no base and fail to parse.
  const src = `${window.location.origin}/mpegts/${encodeURIComponent(name)}`;
  player = mpegts.createPlayer(
    {
      type: 'mpegts',
      url: src,
      isLive: true,
    },
    {
      enableWorker: true,
      liveBufferLatencyChasing: true,
      liveBufferLatencyMaxLatency: 1.5,
      liveBufferLatencyMinRemain: 0.3,
    }
  );
  player.attachMediaElement(video);
  player.load();
  player.play();

  player.on(mpegts.Events.ERROR, (errType: string, errDetail: string) => {
    error.value = `Stream error: ${errType} ${errDetail}`;
  });
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

onUnmounted(destroyPlayer);
</script>

<template>
  <div class="cameras-page">
    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-if="!selected" class="empty">
      Select a camera from the header to view a live stream.
    </div>

    <div v-if="selected" class="video-wrap">
      <video ref="videoEl" class="video" autoplay playsinline />
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

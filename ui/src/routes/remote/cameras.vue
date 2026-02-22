<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Cameras',
  icon: 'camera-viewfinder',
};
</script>

<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import mpegts from 'mpegts.js';
import { useCameraList } from '@/composables/useCameraList';

const route = useRoute();
const router = useRouter();
const { cameras } = useCameraList();

// Stable per-tab identity used to namespace server-side streaming sessions.
// Avoids crypto.randomUUID() which requires a secure context (HTTPS).
const clientId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

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
let stallTimer: ReturnType<typeof setTimeout> | null = null;

function clearStallTimer() {
  if (stallTimer !== null) {
    clearTimeout(stallTimer);
    stallTimer = null;
  }
}

// Attempt to resume playback, restarting the whole stream if the video
// element is truly stuck (readyState too low to play).
function resumePlayback() {
  const video = videoEl.value;
  if (!video || !player) {
    return;
  }
  if (video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
    video.play().catch(() => {});
  } else {
    // Buffer is empty / exhausted — full restart is the only reliable fix.
    startStream();
  }
}

// Attach stall-recovery listeners to the video element.
// Safari can fire 'ended' on a live stream when the buffer runs dry, and
// 'waiting'/'stalled' when it falls behind. We give it a short grace period
// then force resume or restart.
function attachRecoveryListeners(video: HTMLVideoElement) {
  const recover = () => {
    clearStallTimer();
    stallTimer = setTimeout(resumePlayback, 800);
  };
  video.addEventListener('stalled', recover);
  video.addEventListener('waiting', recover);
  video.addEventListener('ended', recover);
  // Also chase liveness: if paused for any reason (e.g. Safari autoplay
  // policy briefly suspending), try to un-pause.
  video.addEventListener('pause', () => {
    if (player) {
      video.play().catch(() => {});
    }
  });
}

function destroyPlayer() {
  clearStallTimer();
  if (player) {
    player.pause();
    player.unload();
    player.detachMediaElement();
    player.destroy();
    player = null;
  }
}

function startStream() {
  destroyPlayer();
  if (!videoEl.value) {
    return;
  }

  const video = videoEl.value;
  // MPEG-TS stream is video-only; keep muted for Safari autoplay compatibility.
  video.muted = true;

  if (!mpegts.isSupported()) {
    error.value = 'MPEG-TS streaming is not supported in this browser.';
    return;
  }

  attachRecoveryListeners(video);

  // Use an absolute URL — mpegts.js fetches inside a Web Worker where
  // relative URLs have no base and fail to parse.
  const src = `${window.location.origin}/mpegts/active?id=${clientId}&camera=${encodeURIComponent(selected.value)}`;
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
  player.play().catch(() => {});

  player.on(mpegts.Events.ERROR, (errType: string, errDetail: string) => {
    error.value = `Stream error: ${errType} ${errDetail}`;
  });
}

async function selectCamera(name: string) {
  if (!name) {
    return;
  }
  await fetch(
    `/mpegts/select?id=${clientId}&camera=${encodeURIComponent(name)}`,
    {
      method: 'POST',
    }
  );
}

watch(selected, async (name) => {
  error.value = '';
  if (player) {
    // Player already running — switch server-side without reconnecting.
    await selectCamera(name);
  } else {
    // No player yet — start one; the camera is embedded in the connect URL.
    await nextTick();
    startStream();
  }
});

// Kick off the initial stream if the page loaded with a ?cam= param.
if (selected.value) {
  nextTick(() => startStream());
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

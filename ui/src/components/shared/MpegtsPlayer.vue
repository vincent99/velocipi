<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue';
import mpegts from 'mpegts.js';

const props = defineProps<{
  cameraName: string;
  clientId: string;
}>();

const videoEl = ref<HTMLVideoElement | null>(null);
const error = ref('');

let player: mpegts.Player | null = null;
let stallTimer: ReturnType<typeof setTimeout> | null = null;

function clearStallTimer() {
  if (stallTimer !== null) {
    clearTimeout(stallTimer);
    stallTimer = null;
  }
}

function resumePlayback() {
  const video = videoEl.value;
  if (!video || !player) {
    return;
  }
  if (video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
    video.play().catch(() => {});
  } else {
    startStream();
  }
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
  if (!videoEl.value || !props.cameraName) {
    return;
  }

  const video = videoEl.value;

  if (!mpegts.isSupported()) {
    error.value = 'MPEG-TS streaming is not supported in this browser.';
    return;
  }

  const src = `${window.location.origin}/mpegts/active?id=${props.clientId}&camera=${encodeURIComponent(props.cameraName)}`;
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
  void player.play();

  player.on(mpegts.Events.ERROR, (errType: string, errDetail: string) => {
    error.value = `Stream error: ${errType} ${errDetail}`;
  });
}

async function selectCamera(name: string) {
  if (!name) {
    return;
  }
  await fetch(
    `/mpegts/select?id=${props.clientId}&camera=${encodeURIComponent(name)}`,
    { method: 'POST' }
  );
}

watch(
  () => props.cameraName,
  async (name) => {
    error.value = '';
    if (!name) {
      return;
    }
    if (player) {
      await selectCamera(name);
    } else {
      await nextTick();
      startStream();
    }
  }
);

if (props.cameraName) {
  nextTick(() => startStream());
}

onMounted(() => {
  window.addEventListener('beforeunload', destroyPlayer);
  const video = videoEl.value;
  if (!video) {
    return;
  }
  video.muted = true;
  const recover = () => {
    clearStallTimer();
    stallTimer = setTimeout(resumePlayback, 800);
  };
  video.addEventListener('stalled', recover);
  video.addEventListener('waiting', recover);
  video.addEventListener('ended', recover);
  video.addEventListener('pause', () => {
    if (player) {
      video.play().catch(() => {});
    }
  });
});
onUnmounted(() => {
  window.removeEventListener('beforeunload', destroyPlayer);
  destroyPlayer();
});
</script>

<template>
  <div class="mpegts-player">
    <div v-if="error" class="player-error">{{ error }}</div>
    <video ref="videoEl" class="player-video" autoplay playsinline />
  </div>
</template>

<style scoped lang="scss">
.mpegts-player {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #000;
}

.player-error {
  background: #5a1a1a;
  border: 1px solid #a33;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  color: #f88;
  flex-shrink: 0;
}

.player-video {
  flex: 1;
  min-height: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
</style>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import RedX from '@/components/RedX.vue';

const props = defineProps<{ name: string; selected?: boolean }>();
const emit = defineEmits<{ (e: 'select', name: string): void }>();

const { cameraRecording } = useDeviceState();
const recording = computed(() => cameraRecording.get(props.name) ?? false);

const blobSrc = ref('');

// snapshotFPS on the server is 1/5 — one frame every 5 seconds.
// Treat the stream as stalled if no frame arrives within 3 intervals.
const STALL_MS = 15_000;

let abortController: AbortController | null = null;
let stallTimer: ReturnType<typeof setTimeout> | null = null;

function clearStallTimer() {
  if (stallTimer !== null) {
    clearTimeout(stallTimer);
    stallTimer = null;
  }
}

function armStallTimer() {
  clearStallTimer();
  stallTimer = setTimeout(() => {
    // No frame arrived in time — reconnect.
    console.log('Stall', props.name);
    connect();
  }, STALL_MS);
}

async function connect() {
  // Cancel any in-flight request.
  abortController?.abort();
  abortController = new AbortController();
  const signal = abortController.signal;

  armStallTimer();

  let response: Response;
  try {
    response = await fetch(`/snapshot/${encodeURIComponent(props.name)}`, {
      signal,
    });
  } catch {
    // aborted or network error — retry handled by stall timer
    return;
  }

  const contentType = response.headers.get('content-type') ?? '';
  // Extract boundary from "multipart/x-mixed-replace; boundary=snapshotboundary"
  const boundaryMatch = contentType.match(/boundary=([^\s;]+)/);
  if (!boundaryMatch || !response.body) {
    return;
  }
  const boundary = '--' + boundaryMatch[1];
  const boundaryBytes = new TextEncoder().encode(boundary);

  const reader = response.body.getReader();
  let buf = new Uint8Array(0);

  const append = (chunk: Uint8Array) => {
    const merged = new Uint8Array(buf.length + chunk.length);
    merged.set(buf);
    merged.set(chunk, buf.length);
    buf = merged;
  };

  // Find needle in haystack, returns index or -1.
  const indexOf = (
    haystack: Uint8Array,
    needle: Uint8Array,
    from = 0
  ): number => {
    outer: for (let i = from; i <= haystack.length - needle.length; i++) {
      for (let j = 0; j < needle.length; j++) {
        if (haystack[i + j] !== needle[j]) {
          continue outer;
        }
      }
      return i;
    }
    return -1;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done || signal.aborted) {
        break;
      }

      append(value);

      // A multipart part looks like:
      //   --boundary\r\nHeaders\r\n\r\nJPEG-data--boundary...
      // Find two consecutive boundary markers to extract one complete part.
      const start = indexOf(buf, boundaryBytes);
      if (start === -1) {
        continue;
      }

      const end = indexOf(buf, boundaryBytes, start + boundaryBytes.length);
      if (end === -1) {
        continue;
      }

      // The part body starts after the first boundary + headers (\r\n\r\n).
      const partHeader = buf.slice(start + boundaryBytes.length, end);
      const headerEnd = indexOf(
        partHeader,
        new Uint8Array([0x0d, 0x0a, 0x0d, 0x0a])
      );
      if (headerEnd === -1) {
        continue;
      }

      const bodyStart = start + boundaryBytes.length + headerEnd + 4;
      // Strip trailing \r\n before the next boundary.
      const bodyEnd = end - 2;

      if (bodyStart < bodyEnd) {
        const jpeg = buf.slice(bodyStart, bodyEnd);
        const blob = new Blob([jpeg], { type: 'image/jpeg' });
        const oldUrl = blobSrc.value;
        blobSrc.value = URL.createObjectURL(blob);
        if (oldUrl) {
          URL.revokeObjectURL(oldUrl);
        }
        armStallTimer(); // reset stall clock on each good frame
      }

      // Consume everything up to the start of the next boundary.
      buf = buf.slice(end);
    }
  } catch {
    // stream error — stall timer will reconnect
  }
}

onMounted(() => {
  connect();
});

// Reconnect if camera name changes (shouldn't happen but be safe).
watch(
  () => props.name,
  () => connect()
);

onUnmounted(() => {
  clearStallTimer();
  abortController?.abort();
  if (blobSrc.value) {
    URL.revokeObjectURL(blobSrc.value);
  }
});
</script>

<template>
  <div
    class="cam-thumb"
    :class="{ active: selected }"
    @click="emit('select', name)"
  >
    <img :src="blobSrc || undefined" class="thumb-img" :alt="name" />
    <RedX v-if="!recording" :stroke-width="3" />
    <span class="thumb-label">{{ name }}</span>
  </div>
</template>

<style scoped lang="scss">
.cam-thumb {
  position: relative;
  height: 100%;
  // Width is auto so the img sets it via aspect-ratio preservation.
  // overflow:hidden keeps the RedX and label clipped to the thumbnail.
  overflow: hidden;
  cursor: pointer;
  border-radius: 3px;
  flex-shrink: 0;

  &:hover {
    outline: 2px solid rgba(255, 255, 255, 0.5);
  }

  &.active {
    outline: 2px solid #fff;
  }
}

.thumb-img {
  display: block;
  height: 100%;
  width: auto;
  min-width: 114px; // 16:9 at 64px height — holds size before first frame
  background: #111;
}

.thumb-label {
  position: absolute;
  bottom: 3px;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 0.65rem;
  font-weight: 700;
  color: #fff;
  // Black outline via text-shadow in all 8 directions.
  text-shadow:
    -1px -1px 0 #000,
    1px -1px 0 #000,
    -1px 1px 0 #000,
    1px 1px 0 #000;
  pointer-events: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 2px;
}
</style>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import RedX from '@/components/RedX.vue';

const props = defineProps<{ name: string }>();
const emit = defineEmits<{ (e: 'select', name: string): void }>();

const { cameraRecording } = useDeviceState();
const recording = computed(() => cameraRecording.get(props.name) ?? false);

const src = ref('');
let timer: ReturnType<typeof setTimeout> | null = null;

async function fetchSnapshot() {
  try {
    const r = await fetch(`/snapshot/${encodeURIComponent(props.name)}`);
    if (r.ok) {
      const intervalSec = parseInt(
        r.headers.get('X-Snapshot-Interval') ?? '5',
        10
      );
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      if (src.value) {
        URL.revokeObjectURL(src.value);
      }
      src.value = url;
      schedule(intervalSec * 1000);
    } else {
      schedule(5000);
    }
  } catch {
    schedule(5000);
  }
}

function schedule(ms: number) {
  if (timer !== null) {
    clearTimeout(timer);
  }
  timer = setTimeout(fetchSnapshot, ms);
}

onMounted(fetchSnapshot);
onUnmounted(() => {
  if (timer !== null) {
    clearTimeout(timer);
  }
  if (src.value) {
    URL.revokeObjectURL(src.value);
  }
});
</script>

<template>
  <div class="cam-thumb" @click="emit('select', name)">
    <img v-if="src" :src="src" class="thumb-img" :alt="name" />
    <div v-else class="thumb-placeholder" />
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
}

.thumb-img,
.thumb-placeholder {
  display: block;
  height: 100%;
  width: auto;
}

.thumb-placeholder {
  // Show something while the first snapshot loads.
  width: 114px; // 16:9 at 64px height
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

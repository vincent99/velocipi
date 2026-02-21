<script setup lang="ts">
import { computed } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import RedX from '@/components/RedX.vue';

const props = defineProps<{ name: string; selected?: boolean }>();
const emit = defineEmits<{ (e: 'select', name: string): void }>();

const { cameraRecording } = useDeviceState();
const recording = computed(() => cameraRecording.get(props.name) ?? false);

const src = computed(() => `/snapshot/${encodeURIComponent(props.name)}`);
</script>

<template>
  <div
    class="cam-thumb"
    :class="{ active: selected }"
    @click="emit('select', name)"
  >
    <img :src="src" class="thumb-img" :alt="name" />
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

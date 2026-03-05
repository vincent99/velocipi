<script setup lang="ts">
import { watch } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import { useVideoViewport } from '@/composables/useVideoViewport';
import MpegtsPlayer from '@/components/shared/MpegtsPlayer.vue';

const { localCamera } = useDeviceState();
const { transformStyle, reset } = useVideoViewport();

const clientId = `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

// Reset zoom/pan whenever the selected camera changes.
watch(localCamera, () => {
  reset();
});
</script>

<template>
  <div class="local-camera">
    <div v-if="localCamera" class="viewport-transform" :style="transformStyle">
      <MpegtsPlayer :camera-name="localCamera" :client-id="clientId" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.local-camera {
  width: 100vw;
  height: 100vh;
  background: #000;
  display: flex;
  overflow: hidden;
}

.viewport-transform {
  flex: 1;
}
</style>

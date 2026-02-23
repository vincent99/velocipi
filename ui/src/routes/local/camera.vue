<script setup lang="ts">
import { useDeviceState } from '@/composables/useDeviceState';
import MpegtsPlayer from '@/components/shared/MpegtsPlayer.vue';

const { localCamera } = useDeviceState();

const clientId = `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
</script>

<template>
  <div class="local-camera">
    <MpegtsPlayer
      v-if="localCamera"
      :camera-name="localCamera"
      :client-id="clientId"
    />
  </div>
</template>

<style scoped lang="scss">
.local-camera {
  width: 100vw;
  height: 100vh;
  background: #000;
  display: flex;
}
</style>

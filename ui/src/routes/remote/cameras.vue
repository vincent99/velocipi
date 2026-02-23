<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Cameras',
  icon: 'camera-viewfinder',
};
</script>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useCameraList } from '@/composables/useCameraList';
import MpegtsPlayer from '@/components/shared/MpegtsPlayer.vue';

const route = useRoute();
const router = useRouter();
const { cameras } = useCameraList();

const clientId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

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
</script>

<template>
  <div class="cameras-page">
    <div v-if="!selected" class="empty">
      Select a camera from the header to view a live stream.
    </div>

    <MpegtsPlayer
      v-if="selected"
      :camera-name="selected"
      :client-id="clientId"
    />
  </div>
</template>

<style scoped lang="scss">
.cameras-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  color: #e0e0e0;
}

.empty {
  color: #666;
  font-size: 0.9rem;
  padding: 2rem 1rem;
}
</style>

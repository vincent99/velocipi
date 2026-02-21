<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Debug',
  icon: 'bug',
  sort: 99,
};
</script>

<script setup lang="ts">
import { useWebSocket } from '@/composables/useWebSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import AirSensor from '@/components/remote/AirSensor.vue';
import TpmsPanel from '@/components/remote/TpmsPanel.vue';
import LedStatus from '@/components/remote/LedStatus.vue';
import KeyRelay from '@/components/shared/KeyRelay.vue';

const { send } = useWebSocket();
const { lastPing, airReading, lux, ledState, tires } = useDeviceState();
</script>

<template>
  <div class="admin">
    <div class="toolbar">
      <span class="ping">{{ lastPing ?? 'Waiting for ping...' }}</span>
      <button @click="send({ type: 'reload' })">Reload</button>
    </div>
    <AirSensor :reading="airReading" :lux="lux" />
    <LedStatus :state="ledState" />
    <TpmsPanel :tires="tires" />
    <KeyRelay />
  </div>
</template>

<style scoped lang="scss">
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.ping {
  font-size: 0.9rem;
  color: #aaa;
}
</style>

<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Debug',
  icon: 'bug',
  sort: 99,
  admin: true,
};
</script>

<script setup lang="ts">
import { computed, isRef, toRaw } from 'vue';
import { useWebSocket } from '@/composables/useWebSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import KeyRelay from '@/components/shared/KeyRelay.vue';
import StateValue from './StateValue.vue';

const { send } = useWebSocket();
const state = useDeviceState();

const stateEntries = computed(() =>
  Object.entries(state)
    .filter(([key]) => key !== 'lastPing')
    .map(([key, val]) => ({
      key,
      value: isRef(val)
        ? toRaw(val.value)
        : Object.fromEntries(toRaw(val) as Map<unknown, unknown>),
    }))
);
</script>

<template>
  <div class="admin">
    <div class="toolbar">
      <span class="ping">{{
        state.lastPing.value ?? 'Waiting for ping...'
      }}</span>
      <button @click="send({ type: 'reload' })">Reload</button>
    </div>
    <section
      v-for="{ key, value } in stateEntries"
      :key="key"
      class="state-section"
    >
      <h3>{{ key }}</h3>
      <StateValue :value="value" />
    </section>
    <KeyRelay />
  </div>
</template>

<style scoped lang="scss">
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.ping {
  font-size: 0.9rem;
  color: #aaa;
  font-family: monospace;
}
.admin {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0.75rem;
}
.state-section {
  margin-bottom: 1.25rem;
}
h3 {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6a9;
  margin: 0 0 0.3rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid #2a2a2a;
}
</style>

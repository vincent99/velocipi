<script setup lang="ts">
import { computed } from 'vue';
import { RouterView } from 'vue-router';
import PageHeader from '@/components/remote/PageHeader.vue';
import RedX from '@/components/RedX.vue';
import { useWebSocket } from '@/composables/useWebSocket';

const { connected, dropped } = useWebSocket();
const wsDisconnected = computed(() => dropped.value && !connected.value);
</script>

<template>
  <div class="remote-layout">
    <PageHeader />
    <main class="remote-main">
      <RouterView />
    </main>

    <Transition name="fade">
      <div v-if="wsDisconnected" class="disconnect-overlay">
        <RedX message="DISCONNECTED" :reload-button="true" />
      </div>
    </Transition>
  </div>
</template>

<style scoped lang="scss">
.remote-layout {
  height: 100vh;
  background: #111;
  color: #eee;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.remote-main {
  flex: 1;
  padding: 1rem;
  min-height: 0; // required so flex child can shrink and fill without overflow
  display: flex;
  flex-direction: column;
}

.disconnect-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

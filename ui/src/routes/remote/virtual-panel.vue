<script lang="ts">
import ScreenViewer from '@/components/remote/ScreenViewer.vue';
import KeyRelay from '@/components/shared/KeyRelay.vue';
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Virtual Panel',
  icon: 'gamepad',
  sort: 98,
};
</script>

<script setup lang="ts"></script>

<template>
  <div>
    <ScreenViewer />
    <KeyRelay />
  </div>
</template>

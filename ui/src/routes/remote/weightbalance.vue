<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'W&B',
  icon: 'balance-scale-left',
  sort: 15,
};
</script>

<script setup lang="ts">
import { watch } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();

// Transparent pass-through: the calculator is the only screen shown at
// /remote/weightbalance itself; Setup is reached via the gear button on the
// calculator, not a visible tab bar.
watch(
  () => route.path,
  (path) => {
    if (path === '/remote/weightbalance') {
      router.replace('/remote/weightbalance/calculator');
    }
  },
  { immediate: true }
);
</script>

<template>
  <div class="wb-layout">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.wb-layout {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: #111;
}
</style>

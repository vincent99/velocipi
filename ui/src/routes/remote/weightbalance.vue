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
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();

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
    <nav class="wb-tabs">
      <RouterLink to="/remote/weightbalance/calculator" class="wb-tab">
        Calculator
      </RouterLink>
      <RouterLink to="/remote/weightbalance/setup" class="wb-tab">
        Setup
      </RouterLink>
    </nav>
    <div class="wb-content">
      <RouterView />
    </div>
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

.wb-tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.5rem 1rem 0;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.wb-tab {
  padding: 0.5rem 1rem;
  color: #aaa;
  text-decoration: none;
  font-size: 0.85rem;
  font-weight: 600;
  border-bottom: 2px solid transparent;

  &:hover {
    color: #e0e0e0;
  }

  &.router-link-active {
    color: #90caf9;
    border-bottom-color: #3b82f6;
  }
}

.wb-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>

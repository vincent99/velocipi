<script setup lang="ts">
import type { Tire } from '@/types/ws';
import TireCard from '@/components/remote/TireCard.vue';

defineProps<{
  tires: Map<string, Tire>;
}>();

const POSITIONS = ['FL', 'FR', 'RL', 'RR'];
</script>

<template>
  <div class="tpms">
    <TireCard
      v-for="pos in POSITIONS"
      :key="pos"
      :position="pos"
      :tire="tires.get(pos) ?? null"
    />
  </div>
</template>

<style scoped lang="scss">
.tpms {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
  margin: 0.75rem 0;
  max-width: 480px;
}
</style>

<script setup lang="ts">
defineProps<{ errors: string[] }>();
</script>

<template>
  <div v-if="errors.length" class="wb-errors">
    <div class="wb-errors-title">
      <i class="fi-sr-triangle-warning" />
      {{ errors.length }} {{ errors.length === 1 ? 'issue' : 'issues' }}
    </div>
    <ul>
      <li v-for="(err, i) in errors" :key="i">{{ err }}</li>
    </ul>
  </div>
  <div v-else class="wb-ok">
    <i class="fi-sr-check" />
    Within limits
  </div>
</template>

<style scoped lang="scss">
.wb-errors {
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 6px;
  padding: 0.6rem 0.85rem;
  color: #f87171;
  font-size: 0.85rem;
}

.wb-errors-title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: 700;
  margin-bottom: 0.35rem;
}

ul {
  margin: 0;
  padding-left: 1.4rem;
}

li {
  margin-bottom: 0.2rem;
}

.wb-ok {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: #4ade80;
  font-size: 0.85rem;
  background: rgba(74, 222, 128, 0.1);
  border: 1px solid rgba(74, 222, 128, 0.3);
  border-radius: 6px;
  padding: 0.5rem 0.85rem;
}
</style>

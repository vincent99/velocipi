<script setup lang="ts">
defineProps<{ title: string; columns?: number }>();
</script>

<template>
  <div class="settings-group">
    <div class="settings-group-header">
      <span class="settings-group-title">{{ title }}</span>
      <slot name="header-action" />
    </div>
    <div
      :style="
        columns
          ? {
              display: 'grid',
              gridTemplateColumns: `repeat(${columns}, 1fr)`,
              gap: '0 0.5rem',
            }
          : {}
      "
    >
      <slot />
    </div>
  </div>
</template>

<style scoped lang="scss">
.settings-group {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.settings-group-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.settings-group-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>

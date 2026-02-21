<script setup lang="ts">
defineProps<{
  message?: string;
  strokeWidth?: number;
  reloadButton?: boolean;
}>();
</script>

<template>
  <div class="red-x-overlay">
    <svg class="red-x-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
      <line x1="0" y1="0" x2="100" y2="100" />
      <line x1="100" y1="0" x2="0" y2="100" />
    </svg>
    <div v-if="message" class="red-x-message">
      <span>{{ message }}</span>
      <button
        v-if="reloadButton"
        class="reload-btn"
        @click="() => location.reload()"
      >
        <i class="fi-sr-rotate-right" />
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.red-x-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.red-x-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;

  line {
    stroke: #e53e3e;
    stroke-width: v-bind('strokeWidth ?? 6');
    vector-effect: non-scaling-stroke;
  }
}

.red-x-message {
  position: relative;
  z-index: 1;
  background: #dc2626;
  color: #fff;
  font-weight: 700;
  font-size: 1.25rem;
  letter-spacing: 0.1em;
  padding: 0.75rem 1.5rem;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  pointer-events: auto;
}

.reload-btn {
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 1rem;
  padding: 0.2rem 0.4rem;
  line-height: 1;

  &:hover {
    background: rgba(0, 0, 0, 0.45);
  }
}
</style>

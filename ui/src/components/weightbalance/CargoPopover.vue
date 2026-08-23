<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  title: string;
  weight: number;
  maxWeight: number;
}>();

const emit = defineEmits<{
  set: [weight: number];
  clear: [];
  cancel: [];
}>();

const value = ref(props.weight);

function submit() {
  emit('set', Math.max(0, value.value || 0));
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('cancel')">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title">{{ title }}</span>
        <button type="button" class="clear-btn" @click="emit('clear')">
          Clear
        </button>
        <button class="modal-close" @click="emit('cancel')">✕</button>
      </div>

      <div class="modal-body">
        <div class="weight-row">
          <div class="weight-slider-wrap">
            <div class="weight-readout">
              {{ value }}
              <span class="unit">/ {{ maxWeight }} lb</span>
            </div>
            <input
              v-model.number="value"
              type="range"
              class="weight-slider"
              min="0"
              :max="maxWeight"
              step="5"
            />
          </div>
          <button type="button" class="set-btn" @click="submit">Set</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.modal-box {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  width: 100%;
  max-width: 320px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #333;
  font-weight: 600;
  color: #e0e0e0;
}

.modal-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-close {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  font-size: 0.9rem;
  flex-shrink: 0;

  &:hover {
    color: #e0e0e0;
  }
}

.modal-body {
  padding: 1rem;
}

.weight-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.weight-slider-wrap {
  flex: 1;
  min-width: 0;
}

.weight-readout {
  font-size: 0.95rem;
  font-weight: 700;
  color: #e0e0e0;
  font-variant-numeric: tabular-nums;
  margin-bottom: 0.15rem;

  .unit {
    font-size: 0.78rem;
    font-weight: 400;
    color: #888;
  }
}

.weight-slider {
  width: 100%;
  accent-color: #3b82f6;
  cursor: pointer;
}

.set-btn {
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  color: #fff;
  padding: 0.4rem 0.9rem;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;

  &:hover {
    background: #2563eb;
  }
}

.clear-btn {
  flex-shrink: 0;
  background: none;
  border: 1px solid rgba(239, 68, 68, 0.5);
  color: #f87171;
  border-radius: 4px;
  padding: 0.35rem 0.6rem;
  font-size: 0.78rem;
  cursor: pointer;

  &:hover {
    background: rgba(239, 68, 68, 0.15);
  }
}
</style>

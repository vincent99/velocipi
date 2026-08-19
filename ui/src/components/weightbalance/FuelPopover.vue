<script setup lang="ts">
import { ref, watch } from 'vue';

const props = defineProps<{
  title: string;
  capacityGal: number;
  gallons: number;
}>();

const emit = defineEmits<{
  update: [gallons: number];
  close: [];
}>();

const value = ref(props.gallons);
watch(
  () => props.gallons,
  (v) => {
    value.value = v;
  }
);

function commit(v: number) {
  value.value = Math.max(0, Math.min(props.capacityGal, v));
  emit('update', value.value);
}

function onSliderInput(e: Event) {
  value.value = parseFloat((e.target as HTMLInputElement).value);
}
function onSliderChange(e: Event) {
  commit(parseFloat((e.target as HTMLInputElement).value));
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal-box">
      <div class="modal-header">
        <span>{{ title }}</span>
        <button class="modal-close" @click="emit('close')">✕</button>
      </div>

      <div class="modal-body">
        <div class="fuel-readout">
          {{ value.toFixed(1) }}
          <span class="unit">/ {{ capacityGal.toFixed(0) }} gal</span>
        </div>
        <input
          class="fuel-slider"
          type="range"
          min="0"
          :max="capacityGal"
          step="0.1"
          :value="value"
          @input="onSliderInput"
          @change="onSliderChange"
        />
        <div class="shortcut-row">
          <button type="button" @click="commit(0)">Empty</button>
          <button type="button" @click="commit(capacityGal / 2)">Half</button>
          <button type="button" @click="commit(capacityGal)">Full</button>
        </div>
      </div>

      <div class="modal-footer">
        <button type="button" class="done-btn" @click="emit('close')">
          Done
        </button>
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
  max-width: 340px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #333;
  font-weight: 600;
  color: #e0e0e0;
}

.modal-close {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  font-size: 0.9rem;

  &:hover {
    color: #e0e0e0;
  }
}

.modal-body {
  padding: 1.25rem 1.25rem 0.5rem;
}

.fuel-readout {
  text-align: center;
  font-size: 1.8rem;
  font-weight: 700;
  color: #e0e0e0;
  margin-bottom: 0.75rem;
  font-variant-numeric: tabular-nums;

  .unit {
    font-size: 1rem;
    font-weight: 400;
    color: #888;
  }
}

.fuel-slider {
  width: 100%;
  -webkit-appearance: none;
  appearance: none;
  height: 3rem;
  background: transparent;
  cursor: pointer;
  touch-action: none;

  &::-webkit-slider-runnable-track {
    height: 0.75rem;
    border-radius: 0.375rem;
    background: rgba(255, 255, 255, 0.15);
  }

  &::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 50%;
    background: #3b82f6;
    margin-top: -0.875rem;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
  }

  &::-moz-range-track {
    height: 0.75rem;
    border-radius: 0.375rem;
    background: rgba(255, 255, 255, 0.15);
  }

  &::-moz-range-thumb {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 50%;
    border: none;
    background: #3b82f6;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
  }
}

.shortcut-row {
  display: flex;
  gap: 0.5rem;
  margin: 0.5rem 0 1rem;

  button {
    flex: 1;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 6px;
    color: #e0e0e0;
    padding: 0.5rem 0;
    font-size: 0.85rem;
    cursor: pointer;

    &:hover {
      border-color: #3b82f6;
      background: #1e3a5f;
    }
  }
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: 0.75rem 1rem;
  border-top: 1px solid #333;
}

.done-btn {
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  color: #fff;
  padding: 0.4rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    background: #2563eb;
  }
}
</style>

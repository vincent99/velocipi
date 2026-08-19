<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  title: string;
  weight: number;
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
        <span>{{ title }}</span>
        <button class="modal-close" @click="emit('cancel')">✕</button>
      </div>

      <div class="modal-body">
        <label class="weight-label">
          Weight (lb)
          <input v-model.number="value" type="number" min="0" autofocus />
        </label>
      </div>

      <div class="modal-footer">
        <button type="button" class="clear-btn" @click="emit('clear')">
          Clear
        </button>
        <div class="footer-right">
          <button type="button" class="cancel-btn" @click="emit('cancel')">
            Cancel
          </button>
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
  max-width: 300px;
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
  padding: 1rem;
}

.weight-label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.82rem;
  color: #999;

  input {
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 0.5rem 0.6rem;
    font-size: 1.2rem;
    font-weight: 600;

    &:focus {
      outline: none;
      border-color: #3b82f6;
    }
  }
}

.modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border-top: 1px solid #333;
}

.footer-right {
  display: flex;
  gap: 0.5rem;
}

.clear-btn {
  background: none;
  border: 1px solid rgba(239, 68, 68, 0.5);
  color: #f87171;
  border-radius: 4px;
  padding: 0.4rem 0.75rem;
  font-size: 0.82rem;
  cursor: pointer;

  &:hover {
    background: rgba(239, 68, 68, 0.15);
  }
}

.cancel-btn {
  background: none;
  border: 1px solid #444;
  color: #aaa;
  border-radius: 4px;
  padding: 0.4rem 0.75rem;
  font-size: 0.82rem;
  cursor: pointer;

  &:hover {
    border-color: #666;
    color: #e0e0e0;
  }
}

.set-btn {
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  color: #fff;
  padding: 0.4rem 0.9rem;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    background: #2563eb;
  }
}
</style>

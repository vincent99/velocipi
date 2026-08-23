<script setup lang="ts">
import { ref } from 'vue';
import type { Person, PositionValue } from '@/types/weightbalance';

const props = defineProps<{
  title: string;
  people: Person[];
  current?: PositionValue;
  maxWeight: number;
}>();

const emit = defineEmits<{
  select: [value: PositionValue];
  clear: [];
  cancel: [];
  'delete-person': [id: string];
}>();

const customName = ref(
  props.current?.personId ? '' : (props.current?.name ?? '')
);
const customWeight = ref(props.current?.weight ?? 0);

function pick(person: Person) {
  emit('select', {
    personId: person.id,
    name: person.name,
    weight: person.weight,
  });
}

function setCustom() {
  if (!customName.value.trim() || customWeight.value <= 0) {
    return;
  }
  emit('select', { name: customName.value.trim(), weight: customWeight.value });
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('cancel')">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title">{{ title }}</span>
        <button type="button" class="clear-btn" @click="emit('clear')">
          Clear seat
        </button>
        <button class="modal-close" @click="emit('cancel')">✕</button>
      </div>

      <div class="modal-body">
        <div v-if="people.length" class="people-list">
          <div v-for="p in people" :key="p.id" class="person-row">
            <button type="button" class="person-btn" @click="pick(p)">
              <span>{{ p.name }}</span>
              <span class="person-weight">{{ p.weight }} lb</span>
            </button>
            <button
              type="button"
              class="delete-person-btn"
              title="Delete person"
              @click="emit('delete-person', p.id)"
            >
              <i class="fi-sr-trash" />
            </button>
          </div>
        </div>
        <p v-else class="hint">
          No saved people yet — set a custom name/weight below to add one.
        </p>

        <div class="custom-section">
          <input
            v-model="customName"
            type="text"
            class="custom-input"
            placeholder="Custom name"
          />
          <div class="custom-weight-row">
            <div class="weight-slider-wrap">
              <div class="weight-readout">
                {{ customWeight }}
                <span class="unit">/ {{ maxWeight }} lb</span>
              </div>
              <input
                v-model.number="customWeight"
                type="range"
                class="weight-slider"
                min="0"
                :max="maxWeight"
                step="5"
              />
            </div>
            <button type="button" class="set-btn" @click="setCustom">
              Set
            </button>
          </div>
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
  max-width: 360px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
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
  padding: 0.85rem 1rem;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.people-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}

.person-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.person-btn {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  color: #e0e0e0;
  cursor: pointer;
  font-size: 0.88rem;

  &:hover {
    border-color: #3b82f6;
    background: #1e3a5f;
  }
}

.person-weight {
  color: #93c5fd;
  font-variant-numeric: tabular-nums;
}

.delete-person-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  padding: 0.4rem;

  &:hover {
    color: #f87171;
  }
}

.hint {
  color: #888;
  font-size: 0.8rem;
  margin: 0 0 0.85rem;
}

.custom-section {
  padding-top: 0.6rem;
  border-top: 1px solid #2a2a2a;
}

.custom-input {
  width: 100%;
  box-sizing: border-box;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.4rem 0.5rem;
  font-size: 0.85rem;
  margin-bottom: 0.6rem;

  &:focus {
    outline: none;
    border-color: #666;
  }
}

.custom-weight-row {
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
  padding: 0.4rem 0.75rem;
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

<script setup lang="ts">
import type { Layout } from '@/types/weightbalance';

const layouts = defineModel<Layout[]>('layouts', { required: true });
const selectedId = defineModel<string | null>('selectedId', { required: true });

function blankLayout(): Layout {
  return {
    id: crypto.randomUUID(),
    name: 'New layout',
    emptyWeight: 0,
    emptyCG: 0,
    gearRetractionMoment: 0,
    maxTakeoffWeight: 0,
    maxLandingWeight: 0,
    maxZeroFuelWeight: 0,
    fuelWeightPerGallon: 6,
    forwardCGLimits: [],
    aftCGLimits: [],
    stations: [],
  };
}

function addLayout() {
  const l = blankLayout();
  layouts.value.push(l);
  selectedId.value = l.id;
}

function duplicateLayout(l: Layout) {
  const copy: Layout = structuredClone({ ...l, hash: undefined });
  copy.id = crypto.randomUUID();
  copy.name = l.name + ' copy';
  layouts.value.push(copy);
  selectedId.value = copy.id;
}

function deleteLayout(l: Layout) {
  const idx = layouts.value.findIndex((x) => x.id === l.id);
  if (idx < 0) {
    return;
  }
  layouts.value.splice(idx, 1);
  if (selectedId.value === l.id) {
    selectedId.value = layouts.value[0]?.id ?? null;
  }
}
</script>

<template>
  <div class="layout-list">
    <button
      v-for="l in layouts"
      :key="l.id"
      type="button"
      class="layout-tab"
      :class="{ active: selectedId === l.id }"
      @click="selectedId = l.id"
    >
      {{ l.name || 'Unnamed' }}
      <span class="seat-count">{{ l.stations.length }} stations</span>
    </button>
    <div class="layout-list-actions">
      <button type="button" class="add-layout-btn" @click="addLayout">
        + Add Layout
      </button>
      <template v-if="selectedId">
        <button
          type="button"
          class="side-btn"
          @click="duplicateLayout(layouts.find((l) => l.id === selectedId)!)"
        >
          Copy
        </button>
        <button
          type="button"
          class="side-btn delete"
          @click="deleteLayout(layouts.find((l) => l.id === selectedId)!)"
        >
          Delete
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.layout-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.layout-tab {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.4rem 0.75rem;
  color: #ccc;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;

  &:hover {
    border-color: #555;
  }

  &.active {
    background: #1e3a5f;
    border-color: #3b82f6;
    color: #90caf9;
  }
}

.seat-count {
  font-size: 0.68rem;
  font-weight: 400;
  color: #888;
}

.layout-list-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}

.add-layout-btn {
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  color: #fff;
  padding: 0.4rem 0.75rem;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    background: #2563eb;
  }
}

.side-btn {
  background: none;
  border: 1px solid #444;
  border-radius: 4px;
  color: #ccc;
  padding: 0.4rem 0.75rem;
  font-size: 0.82rem;
  cursor: pointer;

  &:hover {
    border-color: #666;
  }

  &.delete {
    border-color: rgba(239, 68, 68, 0.5);
    color: #f87171;

    &:hover {
      background: rgba(239, 68, 68, 0.15);
    }
  }
}
</style>

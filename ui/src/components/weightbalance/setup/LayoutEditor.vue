<script setup lang="ts">
import type { CGLimitPoint, Layout, Station } from '@/types/weightbalance';
import StationEditor from './StationEditor.vue';

const layout = defineModel<Layout>('layout', { required: true });

function addLimit(list: CGLimitPoint[]) {
  list.push({ cg: 0, weight: 0 });
}
function removeLimit(list: CGLimitPoint[], idx: number) {
  list.splice(idx, 1);
}

function addStation(type: Station['type']) {
  const base: Station = {
    id: crypto.randomUUID(),
    type,
    name: '',
    arm: 0,
  };
  if (type === 'seat' || type === 'cargo') {
    base.lateral = 'center';
  }
  if (type === 'row') {
    base.seats = [];
  }
  if (type === 'fuel') {
    base.capacityGal = 0;
  }
  layout.value.stations.push(base);
}
function removeStation(idx: number) {
  layout.value.stations.splice(idx, 1);
}
</script>

<template>
  <div class="layout-editor">
    <!-- General -->
    <div class="group">
      <div class="group-title">General</div>
      <div class="general-fields">
        <label
          >Layout name
          <input v-model="layout.name" type="text" placeholder="4 Seat" />
        </label>
        <label
          >Basic empty weight (lb)
          <input v-model.number="layout.emptyWeight" type="number" min="0" />
        </label>
        <label
          >Basic empty CG (in)
          <input v-model.number="layout.emptyCG" type="number" step="0.01" />
        </label>
        <label
          >Gear retraction moment change (in-lb)
          <input
            v-model.number="layout.gearRetractionMoment"
            type="number"
            step="1"
          />
        </label>
        <label
          >Fuel weight per gallon (lb)
          <input
            v-model.number="layout.fuelWeightPerGallon"
            type="number"
            step="0.01"
          />
        </label>
        <label
          >Max takeoff weight (lb)
          <input
            v-model.number="layout.maxTakeoffWeight"
            type="number"
            min="0"
          />
        </label>
        <label
          >Max landing weight (lb)
          <input
            v-model.number="layout.maxLandingWeight"
            type="number"
            min="0"
          />
        </label>
        <label
          >Max zero-fuel weight (lb)
          <input
            v-model.number="layout.maxZeroFuelWeight"
            type="number"
            min="0"
          />
        </label>
      </div>
    </div>

    <!-- CG limits -->
    <div class="cg-limits-grid">
      <div class="group">
        <div class="group-title">Forward CG Limits</div>
        <div class="limit-table-head">
          <span>in</span><span>lbs</span><span></span>
        </div>
        <div
          v-for="(pt, idx) in layout.forwardCGLimits"
          :key="idx"
          class="limit-row"
        >
          <input v-model.number="pt.cg" type="number" step="0.01" />
          <input v-model.number="pt.weight" type="number" step="1" />
          <button
            type="button"
            class="delete-btn"
            @click="removeLimit(layout.forwardCGLimits, idx)"
          >
            Delete
          </button>
        </div>
        <button
          type="button"
          class="add-link"
          @click="addLimit(layout.forwardCGLimits)"
        >
          + Add Forward Limit
        </button>
      </div>

      <div class="group">
        <div class="group-title">Aft CG Limits</div>
        <div class="limit-table-head">
          <span>in</span><span>lbs</span><span></span>
        </div>
        <div
          v-for="(pt, idx) in layout.aftCGLimits"
          :key="idx"
          class="limit-row"
        >
          <input v-model.number="pt.cg" type="number" step="0.01" />
          <input v-model.number="pt.weight" type="number" step="1" />
          <button
            type="button"
            class="delete-btn"
            @click="removeLimit(layout.aftCGLimits, idx)"
          >
            Delete
          </button>
        </div>
        <button
          type="button"
          class="add-link"
          @click="addLimit(layout.aftCGLimits)"
        >
          + Add Aft Limit
        </button>
      </div>
    </div>

    <!-- Stations -->
    <div class="group">
      <div class="group-title">Stations</div>
      <StationEditor
        v-for="(station, idx) in layout.stations"
        :key="station.id"
        :station="station"
        @delete="removeStation(idx)"
      />
      <div class="add-station-row">
        <button type="button" @click="addStation('seat')">+ Seat</button>
        <button type="button" @click="addStation('row')">+ Row of seats</button>
        <button type="button" @click="addStation('cargo')">+ Cargo</button>
        <button type="button" @click="addStation('fuel')">+ Fuel</button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.layout-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.group {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 0.85rem 1.1rem;
}

.group-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.65rem;
}

.general-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.6rem 1rem;

  label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.78rem;
    color: #999;
  }

  input {
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 0.32rem 0.5rem;
    font-size: 0.85rem;

    &:focus {
      outline: none;
      border-color: #666;
    }
  }
}

.cg-limits-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }
}

.limit-table-head {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 0.6rem;
  color: #888;
  font-size: 0.72rem;
  text-transform: uppercase;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid #333;
}

.limit-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 0.6rem;
  align-items: center;
  padding: 0.4rem 0;
  border-bottom: 1px solid #262626;

  input {
    background: none;
    border: none;
    border-bottom: 1px solid #444;
    color: #60a5fa;
    font-weight: 600;
    padding: 0.15rem 0;
    font-size: 0.88rem;

    &:focus {
      outline: none;
      border-color: #3b82f6;
    }
  }
}

.delete-btn {
  background: none;
  border: none;
  color: #f87171;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    color: #fca5a5;
  }
}

.add-link {
  background: none;
  border: none;
  color: #3b82f6;
  font-size: 0.83rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.6rem 0 0.1rem;

  &:hover {
    color: #60a5fa;
  }
}

.add-station-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;

  button {
    background: none;
    border: 1px solid #3b82f6;
    border-radius: 4px;
    color: #3b82f6;
    font-size: 0.8rem;
    padding: 0.35rem 0.7rem;
    cursor: pointer;

    &:hover {
      background: #1e3a5f;
    }
  }
}
</style>

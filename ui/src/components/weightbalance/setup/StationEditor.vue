<script setup lang="ts">
import type { Station } from '@/types/weightbalance';

const station = defineModel<Station>('station', { required: true });

defineEmits<{ delete: [] }>();

function addSeat() {
  station.value.seats = station.value.seats ?? [];
  station.value.seats.push({
    id: crypto.randomUUID(),
    type: 'seat',
    name: '',
    lateral: 'left',
  });
}
function removeSeat(idx: number) {
  station.value.seats?.splice(idx, 1);
}

function weightLimitStr(v: number | undefined): string {
  return v == null ? '' : String(v);
}
function setWeightLimit(raw: string) {
  const n = parseFloat(raw);
  station.value.weightLimit = raw === '' || isNaN(n) ? undefined : n;
}
function setSeatWeightLimit(idx: number, raw: string) {
  const n = parseFloat(raw);
  const seat = station.value.seats?.[idx];
  if (seat) {
    seat.weightLimit = raw === '' || isNaN(n) ? undefined : n;
  }
}

function toggleVariableMoment(enabled: boolean) {
  station.value.variableMoment = enabled
    ? station.value.variableMoment?.length
      ? station.value.variableMoment
      : [{ gallons: 0, momentInLb: 0 }]
    : undefined;
}
function addMomentPoint() {
  station.value.variableMoment = station.value.variableMoment ?? [];
  station.value.variableMoment.push({ gallons: 0, momentInLb: 0 });
}
function removeMomentPoint(idx: number) {
  station.value.variableMoment?.splice(idx, 1);
}
</script>

<template>
  <div class="station-card">
    <div class="station-card-header">
      <input
        v-model="station.name"
        type="text"
        class="station-name"
        placeholder="Station name"
      />
      <select v-model="station.type" class="station-type">
        <option value="seat">Seat</option>
        <option value="row">Row of seats</option>
        <option value="cargo">Cargo</option>
        <option value="fuel">Fuel</option>
      </select>
      <button type="button" class="delete-station-btn" @click="$emit('delete')">
        <i class="fi-sr-trash" />
      </button>
    </div>

    <div class="station-fields">
      <label
        >Arm (in)
        <input v-model.number="station.arm" type="number" step="0.01" />
      </label>
      <label v-if="station.type !== 'fuel'"
        >Weight limit (lb)
        <input
          :value="weightLimitStr(station.weightLimit)"
          type="number"
          min="0"
          placeholder="none"
          @input="setWeightLimit(($event.target as HTMLInputElement).value)"
        />
      </label>

      <label v-if="station.type === 'seat' || station.type === 'cargo'"
        >Lateral
        <select v-model="station.lateral">
          <option value="left">Left</option>
          <option value="center">Center</option>
          <option value="right">Right</option>
          <option value="full">Full</option>
        </select>
      </label>

      <label v-if="station.type === 'seat'" class="checkbox-label"
        ><input v-model="station.ignoreClear" type="checkbox" /> Ignore on
        Clear</label
      >

      <label v-if="station.type === 'fuel'"
        >Capacity (gal)
        <input
          v-model.number="station.capacityGal"
          type="number"
          min="0"
          step="0.1"
        />
      </label>
    </div>

    <!-- Row positions (seats and/or cargo) -->
    <div v-if="station.type === 'row'" class="sub-section">
      <div class="sub-section-header">
        <span>Positions in this row</span>
        <button type="button" class="add-link" @click="addSeat">
          + Add Position
        </button>
      </div>
      <div v-for="(seat, idx) in station.seats" :key="seat.id" class="seat-row">
        <input v-model="seat.name" type="text" placeholder="Name" />
        <select
          :value="seat.type ?? 'seat'"
          @change="
            seat.type = ($event.target as HTMLSelectElement).value as
              | 'seat'
              | 'cargo'
          "
        >
          <option value="seat">Seat</option>
          <option value="cargo">Cargo</option>
        </select>
        <select v-model="seat.lateral">
          <option value="left">Left</option>
          <option value="center">Center</option>
          <option value="right">Right</option>
          <option value="full">Full</option>
        </select>
        <input
          :value="weightLimitStr(seat.weightLimit)"
          type="number"
          min="0"
          placeholder="limit (lb)"
          @input="
            setSeatWeightLimit(idx, ($event.target as HTMLInputElement).value)
          "
        />
        <label v-if="seat.type !== 'cargo'" class="checkbox-label small"
          ><input v-model="seat.ignoreClear" type="checkbox" /> Ignore
          clear</label
        >
        <span v-else />
        <button type="button" class="delete-btn" @click="removeSeat(idx)">
          Delete
        </button>
      </div>
      <p v-if="!station.seats?.length" class="hint">
        No positions in this row yet.
      </p>
    </div>

    <!-- Fuel variable moment table -->
    <div v-if="station.type === 'fuel'" class="sub-section">
      <label class="checkbox-label">
        <input
          type="checkbox"
          :checked="!!station.variableMoment"
          @change="
            toggleVariableMoment(($event.target as HTMLInputElement).checked)
          "
        />
        Variable moment (gallons vs in-lb)
      </label>
      <p class="hint">
        Leave unchecked to use a constant arm (moment = weight × arm). Enable
        for tanks whose CG shifts non-linearly as they drain.
      </p>
      <template v-if="station.variableMoment">
        <div class="moment-table-head">
          <span>Gallons</span>
          <span>Moment (in-lb)</span>
          <span></span>
        </div>
        <div
          v-for="(pt, idx) in station.variableMoment"
          :key="idx"
          class="moment-row"
        >
          <input v-model.number="pt.gallons" type="number" step="0.1" min="0" />
          <input v-model.number="pt.momentInLb" type="number" step="1" />
          <button
            type="button"
            class="delete-btn"
            @click="removeMomentPoint(idx)"
          >
            Delete
          </button>
        </div>
        <button type="button" class="add-link" @click="addMomentPoint">
          + Add point
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.station-card {
  background: #232323;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.75rem 0.9rem;
  margin-bottom: 0.6rem;
}

.station-card-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.station-name {
  flex: 1;
  min-width: 0;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.88rem;
  font-weight: 600;
}

.station-type {
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.82rem;
}

.delete-station-btn {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  padding: 0.2rem;

  &:hover {
    color: #f87171;
  }
}

.station-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem 1rem;
  margin-bottom: 0.25rem;

  label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.75rem;
    color: #999;
  }

  input,
  select {
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 0.3rem 0.45rem;
    font-size: 0.82rem;
    width: 120px;
  }
}

.checkbox-label {
  flex-direction: row !important;
  align-items: center;
  gap: 0.35rem !important;

  input {
    width: auto !important;
    accent-color: #3b82f6;
  }

  &.small {
    font-size: 0.72rem;
    white-space: nowrap;
  }
}

.sub-section {
  border-top: 1px solid #2a2a2a;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
}

.sub-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.78rem;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-bottom: 0.4rem;
}

.add-link {
  background: none;
  border: none;
  color: #3b82f6;
  font-size: 0.8rem;
  cursor: pointer;

  &:hover {
    color: #60a5fa;
  }
}

.seat-row {
  display: grid;
  grid-template-columns: 1.3fr 0.8fr 0.8fr 0.8fr auto auto;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.35rem;

  input,
  select {
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 0.28rem 0.4rem;
    font-size: 0.8rem;
    min-width: 0;
  }
}

.moment-table-head {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 0.5rem;
  font-size: 0.72rem;
  color: #888;
  margin-bottom: 0.2rem;
}

.moment-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.3rem;

  input {
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 0.28rem 0.4rem;
    font-size: 0.8rem;
    min-width: 0;
  }
}

.delete-btn {
  background: none;
  border: none;
  color: #f87171;
  font-size: 0.78rem;
  cursor: pointer;
  white-space: nowrap;

  &:hover {
    color: #fca5a5;
  }
}

.hint {
  color: #666;
  font-size: 0.75rem;
  margin: 0.2rem 0 0.5rem;
}
</style>

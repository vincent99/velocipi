<script lang="ts">
import { defineComponent, computed, h } from 'vue';
import type { PanelMeta } from '@/types/config';
import { useDeviceState } from '@/composables/useDeviceState';

// Mini header component: 2x2 grid of mode / fan / setpoint / current temp.
const AirConHeader = defineComponent({
  name: 'AirConHeader',
  setup() {
    const { airConState } = useDeviceState();
    const mode = computed(() => airConState.value?.mode ?? '—');
    const fan = computed(() => airConState.value?.fan ?? '—');
    const setpoint = computed(() => {
      const sp = airConState.value?.setpoint;
      return sp != null ? sp.toFixed(0) + '°' : '—';
    });
    const currTemp = computed(() => {
      const t = airConState.value?.currentTemp;
      return t != null ? t.toFixed(1) + '°' : '—';
    });

    return () =>
      h('div', { class: 'ac-hdr' }, [
        h('div', { class: 'ac-cell' }, [
          h('span', { class: 'ac-lbl' }, 'Mode'),
          h('span', { class: 'ac-val' }, mode.value),
        ]),
        h('div', { class: 'ac-cell' }, [
          h('span', { class: 'ac-lbl' }, 'Fan'),
          h('span', { class: 'ac-val' }, fan.value),
        ]),
        h('div', { class: 'ac-cell' }, [
          h('span', { class: 'ac-lbl' }, 'Set'),
          h('span', { class: 'ac-val' }, setpoint.value),
        ]),
        h('div', { class: 'ac-cell' }, [
          h('span', { class: 'ac-lbl' }, 'Temp'),
          h('span', { class: 'ac-val' }, currTemp.value),
        ]),
      ]);
  },
});

export const remoteMeta: PanelMeta = {
  name: 'Air Con',
  icon: 'snowflake',
  sort: 5,
};

export const headerComponent = AirConHeader;
</script>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';

const { airConState } = useDeviceState();

const busy = ref(false);
const lastError = ref('');

async function set(field: string, value: string) {
  busy.value = true;
  lastError.value = '';
  try {
    const r = await fetch('/aircon/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field, value }),
    });
    if (!r.ok) {
      lastError.value = await r.text();
    }
  } catch (e: unknown) {
    lastError.value = String(e);
  } finally {
    busy.value = false;
  }
}

const state = computed(() => airConState.value);
const connected = computed(() => state.value?.connected ?? false);

// Setpoint editing
const setpointInput = ref('');
const setpointEditing = ref(false);

function startEditSetpoint() {
  setpointInput.value = state.value?.setpoint?.toFixed(1) ?? '72.0';
  setpointEditing.value = true;
}

async function commitSetpoint() {
  setpointEditing.value = false;
  const v = parseFloat(setpointInput.value);
  if (!isNaN(v)) {
    await set('setpoint', v.toFixed(2));
  }
}

// Delta editing
const deltaInput = ref('');
const deltaEditing = ref(false);

function startEditDelta() {
  deltaInput.value = state.value?.delta?.toFixed(1) ?? '2.0';
  deltaEditing.value = true;
}

async function commitDelta() {
  deltaEditing.value = false;
  const v = parseFloat(deltaInput.value);
  if (!isNaN(v)) {
    await set('delta', v.toFixed(2));
  }
}

function fmt(v: number | null | undefined, digits = 1): string {
  return v != null ? v.toFixed(digits) + '°F' : '—';
}
</script>

<template>
  <div class="aircon-page">
    <div v-if="!connected" class="ac-disconnected">
      <i class="fi-sr-snowflake" />
      <span>Air conditioner not connected</span>
    </div>

    <template v-else>
      <!-- Status banner -->
      <div v-if="lastError" class="ac-error">{{ lastError }}</div>

      <!-- Controls -->
      <div class="ac-section">
        <h2>Mode</h2>
        <div class="ac-btn-row">
          <button
            v-for="m in ['off', 'fan', 'auto', 'cool']"
            :key="m"
            class="ac-btn"
            :class="{ active: state?.mode === m }"
            :disabled="busy"
            @click="set('mode', m)"
          >
            {{ m }}
          </button>
        </div>
      </div>

      <div class="ac-section">
        <h2>Fan Speed</h2>
        <div class="ac-btn-row">
          <button
            v-for="f in ['low', 'medium', 'high']"
            :key="f"
            class="ac-btn"
            :class="{ active: state?.fan === f }"
            :disabled="busy"
            @click="set('fan', f)"
          >
            {{ f }}
          </button>
        </div>
      </div>

      <div class="ac-section">
        <h2>Circulation</h2>
        <div class="ac-btn-row">
          <button
            v-for="c in ['recirc', 'fresh']"
            :key="c"
            class="ac-btn"
            :class="{ active: state?.circulation === c }"
            :disabled="busy"
            @click="set('circ', c)"
          >
            {{ c }}
          </button>
        </div>
      </div>

      <div class="ac-section">
        <h2>Setpoint</h2>
        <div v-if="!setpointEditing" class="ac-value-row">
          <span class="ac-big-val">{{ state?.setpoint?.toFixed(1) }}°F</span>
          <button class="ac-edit-btn" @click="startEditSetpoint">Edit</button>
        </div>
        <div v-else class="ac-value-row">
          <input
            v-model="setpointInput"
            type="number"
            step="0.5"
            class="ac-input"
            @keydown.enter="commitSetpoint"
            @keydown.escape="setpointEditing = false"
          />
          <button class="ac-edit-btn" @click="commitSetpoint">Set</button>
          <button class="ac-edit-btn" @click="setpointEditing = false">
            Cancel
          </button>
        </div>
      </div>

      <div class="ac-section">
        <h2>Hysteresis (Delta)</h2>
        <div v-if="!deltaEditing" class="ac-value-row">
          <span class="ac-big-val">{{ state?.delta?.toFixed(1) }}°F</span>
          <button class="ac-edit-btn" @click="startEditDelta">Edit</button>
        </div>
        <div v-else class="ac-value-row">
          <input
            v-model="deltaInput"
            type="number"
            step="0.5"
            class="ac-input"
            @keydown.enter="commitDelta"
            @keydown.escape="deltaEditing = false"
          />
          <button class="ac-edit-btn" @click="commitDelta">Set</button>
          <button class="ac-edit-btn" @click="deltaEditing = false">
            Cancel
          </button>
        </div>
      </div>

      <!-- Status readings -->
      <div class="ac-section">
        <h2>Temperatures</h2>
        <div class="ac-readings">
          <div class="ac-reading">
            <span class="ac-reading-lbl">Current</span>
            <span class="ac-reading-val">{{ fmt(state?.currentTemp) }}</span>
          </div>
          <div class="ac-reading">
            <span class="ac-reading-lbl">Cabin</span>
            <span class="ac-reading-val">{{ fmt(state?.cabinTemp) }}</span>
          </div>
          <div class="ac-reading">
            <span class="ac-reading-lbl">Panel</span>
            <span class="ac-reading-val">{{ fmt(state?.panelTemp) }}</span>
          </div>
          <div class="ac-reading">
            <span class="ac-reading-lbl">Blower</span>
            <span class="ac-reading-val">{{ fmt(state?.blowerTemp) }}</span>
          </div>
          <div class="ac-reading">
            <span class="ac-reading-lbl">Exhaust</span>
            <span class="ac-reading-val">{{ fmt(state?.exhaustTemp) }}</span>
          </div>
          <div class="ac-reading">
            <span class="ac-reading-lbl">Baggage</span>
            <span class="ac-reading-val">{{ fmt(state?.baggageTemp) }}</span>
          </div>
          <div class="ac-reading">
            <span class="ac-reading-lbl">Tail</span>
            <span class="ac-reading-val">{{ fmt(state?.tailTemp) }}</span>
          </div>
        </div>
      </div>

      <div class="ac-section">
        <h2>Compressor</h2>
        <div class="ac-comp-status" :class="{ on: state?.compressor }">
          {{ state?.compressor ? 'ON' : 'OFF' }}
        </div>
      </div>

      <div v-if="state?.error" class="ac-section">
        <h2>Error</h2>
        <div class="ac-error-val">{{ state.error }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.aircon-page {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.ac-disconnected {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: #888;
  font-size: 1rem;
  padding: 2rem 0;

  i {
    font-size: 1.5rem;
  }
}

.ac-error {
  background: rgba(239, 68, 68, 0.2);
  border: 1px solid rgba(239, 68, 68, 0.5);
  border-radius: 4px;
  padding: 0.5rem 0.75rem;
  color: #f87171;
  font-size: 0.875rem;
}

.ac-section {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  padding: 0.75rem 1rem;

  h2 {
    font-size: 0.75rem;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0 0 0.5rem;
  }
}

.ac-btn-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.ac-btn {
  padding: 0.4rem 1rem;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-size: 0.9rem;
  text-transform: capitalize;
  transition: background 0.15s;

  &:hover {
    background: rgba(255, 255, 255, 0.15);
  }

  &.active {
    background: rgba(59, 130, 246, 0.4);
    border-color: rgba(59, 130, 246, 0.8);
    color: #93c5fd;
  }

  &:disabled {
    opacity: 0.5;
    cursor: default;
  }
}

.ac-value-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.ac-big-val {
  font-size: 1.4rem;
  font-weight: 600;
  color: #e0e0e0;
  min-width: 5rem;
}

.ac-edit-btn {
  padding: 0.3rem 0.75rem;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  color: #aaa;
  cursor: pointer;
  font-size: 0.8rem;

  &:hover {
    background: rgba(255, 255, 255, 0.15);
    color: #e0e0e0;
  }
}

.ac-input {
  width: 7rem;
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 1.1rem;
  padding: 0.3rem 0.5rem;
}

.ac-readings {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.5rem;
}

.ac-reading {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.ac-reading-lbl {
  font-size: 0.7rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ac-reading-val {
  font-size: 1.1rem;
  font-weight: 600;
  color: #e0e0e0;
}

.ac-comp-status {
  font-size: 1.2rem;
  font-weight: 700;
  color: #888;
  padding: 0.25rem 0;

  &.on {
    color: #4ade80;
  }
}

.ac-error-val {
  color: #f87171;
  font-size: 0.9rem;
}
</style>

<style lang="scss">
/* Global styles for the AirCon header component in the nav bar */
.ac-hdr {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  width: 100%;
  height: 100%;
  padding: 2px;
  box-sizing: border-box;
  gap: 1px;
}

.ac-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.ac-lbl {
  font-size: 0.45rem;
  color: rgba(255, 255, 255, 0.6);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ac-val {
  font-size: 0.65rem;
  font-weight: 600;
  color: #fff;
}
</style>

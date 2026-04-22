<script lang="ts">
import { defineComponent, computed, h } from 'vue';
import type { PanelMeta } from '@/types/config';
import { useDeviceState } from '@/composables/useDeviceState';
import RedX from '@/components/RedX.vue';

const modeIcon: Record<string, string> = {
  off: 'fi-sr-power-off',
  fan: 'fi-sr-wind',
  auto: 'fi-sr-user-robot',
  cool: 'fi-sr-snowflake',
};
const fanIcon: Record<string, string> = {
  off: 'fi-sr-signal-alt-slash',
  low: 'fi-sr-signal-alt',
  medium: 'fi-sr-signal-alt-1',
  high: 'fi-sr-signal-alt-2',
};

// Mini header component: top row = mode icon + fan icon; bottom row = current temp + setpoint.
const AirConHeader = defineComponent({
  name: 'AirConHeader',
  setup() {
    const { airConState } = useDeviceState();
    const connected = computed(() => airConState.value?.connected ?? false);
    const modeIconClass = computed(
      () => modeIcon[airConState.value?.mode ?? ''] ?? 'fi-sr-power-off'
    );
    const fanIconClass = computed(
      () => fanIcon[airConState.value?.fan ?? ''] ?? 'fi-sr-signal-alt-slash'
    );
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
          h('i', { class: modeIconClass.value }),
        ]),
        h('div', { class: 'ac-cell' }, [h('i', { class: fanIconClass.value })]),
        h('div', { class: 'ac-cell' }, [
          h('span', { class: 'ac-val' }, setpoint.value),
        ]),
        h('div', { class: 'ac-cell' }, [
          h('span', { class: 'ac-val' }, currTemp.value),
        ]),
        !connected.value ? h(RedX, { strokeWidth: 3 }) : null,
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
import { ref, computed, watch } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import LineGraph from '@/components/remote/LineGraph.vue';
import RedX from '@/components/RedX.vue';
import type { GraphSeries } from '@/components/remote/LineGraph.vue';

const { airConState, g3xState, airConHistory } = useDeviceState();

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
const mode = computed(() => state.value?.mode ?? 'off');

const fanDisabled = computed(
  () => busy.value || mode.value === 'off' || mode.value === 'auto'
);
const setpointDisabled = computed(
  () => busy.value || mode.value === 'off' || mode.value === 'fan'
);
const circDisabled = computed(
  () => busy.value || mode.value === 'off' || mode.value === 'auto'
);

// Setpoint slider — tracks server state; live display while dragging
const dragging = ref(false);
const sliderValue = ref(state.value?.setpoint ?? 72);

watch(
  () => state.value?.setpoint,
  (v) => {
    if (v != null && !dragging.value) {
      sliderValue.value = v;
    }
  }
);

const sliderMin = computed(() => {
  const sp = state.value?.setpoint ?? 72;
  return Math.min(60, Math.floor(sp));
});

const sliderMax = computed(() => {
  const sp = state.value?.setpoint ?? 72;
  return Math.max(80, Math.ceil(sp));
});

function onSliderInput(e: Event) {
  dragging.value = true;
  sliderValue.value = parseFloat((e.target as HTMLInputElement).value);
}

async function onSliderChange(e: Event) {
  const v = parseFloat((e.target as HTMLInputElement).value);
  sliderValue.value = v;
  dragging.value = false;
  await set('setpoint', v.toFixed(2));
}

function fmt(v: number | null | undefined, digits = 1): string {
  return v != null ? v.toFixed(digits) + '°F' : '—';
}

const oatLabel = computed(() => {
  const oat = g3xState.value?.oatCelsius;
  return oat != null ? ((oat * 9) / 5 + 32).toFixed(0) + '°F' : '—';
});

// ── Temperature history graph ─────────────────────────────────────────────
// Colors from the Okabe-Ito colorblind-safe palette; patterns further
// distinguish lines for monochromacy. "Current" is bold white — most important.

interface SensorDef {
  key: keyof (typeof airConHistory.value)[0];
  name: string;
  color: string;
  strokeWidth?: number;
  strokeDasharray?: string;
}

const sensorDefs: SensorDef[] = [
  // Bold solid white — the primary control temperature
  {
    key: 'currentTemp',
    name: 'Current',
    color: '#ffffff',
    strokeWidth: 2.5,
  },
  // Vivid sky blue, solid
  { key: 'cabinTemp', name: 'Cabin', color: '#34C6FF' },
  // Vivid green, long dash
  {
    key: 'blowerTemp',
    name: 'Blower',
    color: '#00E5A0',
    strokeDasharray: '8,4',
  },
  // Vivid amber, short dash
  {
    key: 'exhaustTemp',
    name: 'Exhaust',
    color: '#FFB800',
    strokeDasharray: '4,3',
  },
  // Hot pink, dot-dash
  {
    key: 'panelTemp',
    name: 'Panel',
    color: '#FF5FBD',
    strokeDasharray: '6,3,2,3',
  },
  // Vivid orange-red, dots
  {
    key: 'baggageTemp',
    name: 'Baggage',
    color: '#FF5500',
    strokeDasharray: '2,4',
  },
  // Vivid blue, long dash-dot
  {
    key: 'tailTemp',
    name: 'Tail',
    color: '#2196FF',
    strokeDasharray: '10,3,2,3',
  },
  // Light gray, long dash — external source, visually secondary
  { key: 'oat', name: 'OAT', color: '#cccccc', strokeDasharray: '12,4' },
];

const graphSeries = computed<GraphSeries[]>(() => {
  const hist = airConHistory.value;
  return sensorDefs
    .map((def) => ({
      name: def.name,
      color: def.color,
      strokeWidth: def.strokeWidth,
      strokeDasharray: def.strokeDasharray,
      data: hist.map((s) => ({
        time: new Date(s.time),
        value: (s[def.key] as number | undefined) ?? null,
      })),
    }))
    .filter((s) => s.data.some((d) => d.value !== null && d.value !== 0));
});
</script>

<template>
  <div class="aircon-page">
    <RedX v-if="!connected" message="Air conditioner not connected" />

    <template v-else>
      <!-- Status banner -->
      <div v-if="lastError" class="ac-error">{{ lastError }}</div>

      <!-- Combined mode / fan / circ + setpoint -->
      <div class="ac-section">
        <div class="ac-mode-grid">
          <div class="ac-mode-group">
            <div class="ac-group-lbl">Mode</div>
            <div class="ac-btn-col">
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
          <div class="ac-mode-group">
            <div class="ac-group-lbl">Fan</div>
            <div class="ac-btn-col">
              <button
                v-for="f in ['low', 'medium', 'high']"
                :key="f"
                class="ac-btn"
                :class="{ active: state?.fan === f }"
                :disabled="fanDisabled"
                @click="set('fan', f)"
              >
                {{ f }}
              </button>
            </div>
          </div>
          <div class="ac-mode-group">
            <div class="ac-group-lbl">Circulation</div>
            <div class="ac-btn-col">
              <button
                v-for="c in ['recirc', 'fresh']"
                :key="c"
                class="ac-btn"
                :class="{ active: state?.circulation === c }"
                :disabled="circDisabled"
                @click="set('circ', c)"
              >
                {{ c }}
              </button>
            </div>
          </div>
        </div>

        <!-- Setpoint row -->
        <div class="ac-setpoint-row">
          <span class="ac-big-val" :class="{ disabled: setpointDisabled }"
            >{{ sliderValue.toFixed(0) }}°F</span
          >
          <input
            class="ac-slider"
            type="range"
            :min="sliderMin"
            :max="sliderMax"
            step="1"
            :value="sliderValue"
            :disabled="setpointDisabled"
            @input="onSliderInput"
            @change="onSliderChange"
          />
        </div>
      </div>

      <!-- Status readings + compressor -->
      <div class="ac-section">
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
            <span class="ac-reading-lbl">Compressor</span>
            <span
              class="ac-reading-val"
              :class="{ 'ac-comp-on': state?.compressor === 'on' }"
            >
              {{
                state?.compressor != null ? state.compressor.toUpperCase() : '—'
              }}
            </span>
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
          <div class="ac-reading">
            <span class="ac-reading-lbl">OAT</span>
            <span class="ac-reading-val">{{ oatLabel }}</span>
          </div>
        </div>
      </div>

      <div v-if="state?.error" class="ac-section">
        <h2>Error</h2>
        <div class="ac-error-val">{{ state.error }}</div>
      </div>

      <!-- Temperature history graph -->
      <div v-if="graphSeries.length" class="ac-section">
        <h2>Temperature History</h2>
        <LineGraph
          :series="graphSeries"
          :height="200"
          :y-min="60"
          :y-max="120"
        />
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

// Mode / fan / circ — 3 rows on phone, 3 columns on tablet+
.ac-mode-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;

  @media (min-width: 640px) {
    flex-direction: row;
    gap: 1rem;

    .ac-mode-group {
      flex: 1;
    }
  }
}

.ac-group-lbl {
  font-size: 0.7rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.35rem;
}

.ac-btn-col {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 0.4rem;

  @media (min-width: 640px) {
    flex-direction: column;
    flex-wrap: nowrap;
  }
}

.ac-btn {
  padding: 0.5rem 1rem;
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

// Setpoint row — large value + full-width slider
.ac-setpoint-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.ac-big-val {
  font-size: 1.8rem;
  font-weight: 700;
  color: #e0e0e0;
  min-width: 5.5rem;
  text-align: right;
  flex-shrink: 0;

  &.disabled {
    opacity: 0.4;
  }
}

// Chunky touch-friendly range slider
.ac-slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 3rem;
  background: transparent;
  cursor: pointer;
  touch-action: none;

  &:disabled {
    opacity: 0.4;
    cursor: default;
  }

  &::-webkit-slider-runnable-track {
    height: 0.75rem;
    border-radius: 0.375rem;
    background: rgba(255, 255, 255, 0.15);
  }

  &::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 2.75rem;
    height: 2.75rem;
    border-radius: 50%;
    background: #3b82f6;
    margin-top: -1rem;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
  }

  &::-moz-range-track {
    height: 0.75rem;
    border-radius: 0.375rem;
    background: rgba(255, 255, 255, 0.15);
  }

  &::-moz-range-thumb {
    width: 2.75rem;
    height: 2.75rem;
    border-radius: 50%;
    border: none;
    background: #3b82f6;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
  }
}

.ac-readings {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
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

.ac-comp-on {
  color: #4ade80;
}

.ac-error-val {
  color: #f87171;
  font-size: 0.9rem;
}
</style>

<style lang="scss">
/* Global styles for the AirCon header component in the nav bar */
.ac-hdr {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  width: 100%;
  height: 100%;
  padding: 2px;
  box-sizing: border-box;
  gap: 1px;
}

/* top row: icons pushed toward the midline */
.ac-hdr .ac-cell:nth-child(-n + 2) {
  align-items: center;
  justify-content: flex-end;
  padding-bottom: 1px;
}

/* bottom row: temps pushed toward the midline */
.ac-hdr .ac-cell:nth-child(3),
.ac-hdr .ac-cell:nth-child(4) {
  align-items: center;
  justify-content: flex-start;
  padding-top: 1px;
}

.ac-cell {
  display: flex;
  flex-direction: column;
  line-height: 1;

  i {
    font-size: 1.1rem;
    color: #fff;
  }
}

.ac-val {
  font-size: 0.75rem;
  font-weight: 600;
  color: #fff;
}
</style>

<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const panelMeta: PanelMeta = {
  name: 'Air Con',
  icon: 'snowflake',
  sort: 2,
};
</script>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useWebSocket } from '@/composables/useWebSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import PanelGrid from '@/components/panel/PanelGrid.vue';
import PanelSelect from '@/components/panel/PanelSelect.vue';
import PanelValue from '@/components/panel/PanelValue.vue';
import SparkLine from '@/components/panel/SparkLine.vue';
import RedX from '@/components/RedX.vue';
import type { SelectOption } from '@/components/panel/PanelSelect.vue';

void useWebSocket; // WS not used directly but needed for reactivity

const { airConState, g3xState, airConHistory } = useDeviceState();

const state = computed(() => airConState.value);
const connected = computed(() => state.value?.connected ?? false);
const mode = computed(() => state.value?.mode ?? 'off');

// ── Disable logic per mode ─────────────────────────────────────────────────
// off:  fan, setpoint, recirc all disabled
// fan:  setpoint disabled; fan + recirc available
// auto: fan + recirc disabled; setpoint available
// cool: all available
const fanDisabled = computed(
  () => mode.value === 'off' || mode.value === 'auto'
);
const setpointDisabled = computed(
  () => mode.value === 'off' || mode.value === 'fan'
);
const circDisabled = computed(
  () => mode.value === 'off' || mode.value === 'auto'
);

// ── Selectors ──────────────────────────────────────────────────────────────

const modeOptions: SelectOption[] = [
  { name: 'Off', value: 'off', icon: 'power-off' },
  { name: 'Fan', value: 'fan', icon: 'wind' },
  { name: 'Auto', value: 'auto', icon: 'user-robot' },
  { name: 'Cool', value: 'cool', icon: 'snowflake' },
];

const fanOptions: SelectOption[] = [
  { name: 'Off', value: 'off', icon: 'signal-alt-slash' },
  { name: 'Low', value: 'low', icon: 'signal-alt' },
  { name: 'Med', value: 'medium', icon: 'signal-alt-1' },
  { name: 'High', value: 'high', icon: 'signal-alt-2' },
];

const circOptions: SelectOption[] = [
  { name: 'Recirc', value: 'recirc', icon: 'recycle' },
  { name: 'Fresh', value: 'fresh', icon: 'wind' },
];

const busy = ref(false);

async function airconSet(field: string, value: string) {
  if (busy.value) {
    return;
  }
  busy.value = true;
  try {
    await fetch('/aircon/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field, value }),
    });
  } finally {
    busy.value = false;
  }
}

// Setpoint: full range 60–85°F so the knob can scroll freely to any value.
const setpointOptions: SelectOption[] = Array.from({ length: 26 }, (_, i) => ({
  name: `${60 + i}°F`,
  value: String(60 + i),
}));
const setpointValue = computed(() =>
  String(Math.round(state.value?.setpoint ?? 72))
);

function fmt(v: number | null | undefined): string {
  if (v == null) {
    return '—';
  }
  return v.toFixed(v >= 100 ? 0 : 1);
}

const compLabel = computed(() => {
  const c = state.value?.compressor;
  return c != null ? c.toUpperCase() : '—';
});

const oatLabel = computed(() => {
  const oat = g3xState.value?.oatCelsius;
  return oat != null ? ((oat * 9) / 5 + 32).toFixed(0) : '—';
});

const sparkData = computed(() =>
  airConHistory.value.map((s) => ({
    time: new Date(s.time),
    value: s.currentTemp ?? null,
  }))
);
</script>

<template>
  <PanelGrid>
    <RedX v-if="!connected" :stroke-width="3" message="BT" />

    <!-- Col 1–4, Row 1: Setpoint selector -->
    <PanelSelect
      :col="1"
      :row="1"
      :col-span="4"
      :row-span="1"
      :options="setpointOptions"
      :model-value="setpointValue"
      :disabled="setpointDisabled"
      :wrap="false"
      @update:model-value="
        (v) => airconSet('setpoint', parseFloat(v).toFixed(2))
      "
    />

    <!-- Col 1–4, Row 2: Recirc / Fresh selector -->
    <PanelSelect
      :col="1"
      :row="2"
      :col-span="4"
      :row-span="1"
      :options="circOptions"
      :model-value="state?.circulation ?? 'recirc'"
      :disabled="circDisabled"
      @update:model-value="(v) => airconSet('circ', v)"
    />

    <!-- Col 1–4, Row 3: Front (panel) temp -->
    <PanelValue
      :col="1"
      :row="3"
      :col-span="4"
      label="Front"
      :model-value="fmt(state?.panelTemp)"
    />

    <!-- Col 1–4, Row 4: Rear (cabin) temp -->
    <PanelValue
      :col="1"
      :row="4"
      :col-span="4"
      label="Rear"
      :model-value="fmt(state?.cabinTemp)"
    />

    <!-- Col 5–8, Row 1: Mode selector -->
    <PanelSelect
      :col="5"
      :row="1"
      :col-span="4"
      :options="modeOptions"
      :model-value="state?.mode ?? 'off'"
      @update:model-value="(v) => airconSet('mode', v)"
    />

    <!-- Col 5–8, Row 2: Fan speed selector -->
    <PanelSelect
      :col="5"
      :row="2"
      :col-span="4"
      :options="fanOptions"
      :model-value="state?.fan ?? 'low'"
      :disabled="fanDisabled"
      @update:model-value="(v) => airconSet('fan', v)"
    />

    <!-- Col 5–8, Row 3: Blower temp -->
    <PanelValue
      :col="5"
      :row="3"
      :col-span="4"
      label="Blower"
      :model-value="fmt(state?.blowerTemp)"
    />

    <!-- Col 5–8, Row 4: Compressor status -->
    <PanelValue
      :col="5"
      :row="4"
      :col-span="4"
      label="Compress"
      :model-value="compLabel"
    />

    <!-- Col 9–16, Rows 1–2: Current temp sparkline -->
    <SparkLine
      :col="9"
      :row="1"
      :col-span="8"
      :row-span="2"
      :data="sparkData"
      :y-min="72"
      :y-max="100"
      :reference="state?.setpoint"
    />

    <!-- Col 9–12, Row 3: Baggage temp -->
    <PanelValue
      :col="9"
      :row="3"
      :col-span="4"
      label="Baggage"
      :model-value="fmt(state?.baggageTemp)"
    />

    <!-- Col 9–12, Row 4: Tail temp -->
    <PanelValue
      :col="9"
      :row="4"
      :col-span="4"
      label="Tail"
      :model-value="fmt(state?.tailTemp)"
    />

    <!-- Col 13–16, Row 3: Exhaust temp -->
    <PanelValue
      :col="13"
      :row="3"
      :col-span="4"
      label="Exhaust"
      :model-value="fmt(state?.exhaustTemp)"
    />

    <!-- Col 13–16, Row 4: Outside air temp (from G3X) -->
    <PanelValue
      :col="13"
      :row="4"
      :col-span="4"
      label="Outside"
      :model-value="oatLabel"
    />
  </PanelGrid>
</template>

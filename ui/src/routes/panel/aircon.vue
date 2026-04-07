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
import type { SelectOption } from '@/components/panel/PanelSelect.vue';

void useWebSocket; // WS not used directly but needed for reactivity

const { airConState, g3xState } = useDeviceState();

const state = computed(() => airConState.value);
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

// Setpoint: nudge ±1°F via inner knob through the select.
const setpointOptions = computed<SelectOption[]>(() => {
  const sp = state.value?.setpoint ?? 72;
  return [
    { name: (sp - 1).toFixed(0) + '°F', value: String(sp - 1) },
    { name: sp.toFixed(0) + '°F', value: String(sp) },
    { name: (sp + 1).toFixed(0) + '°F', value: String(sp + 1) },
  ];
});
const setpointValue = computed(() => String(state.value?.setpoint ?? 72));

function fmt(v: number | null | undefined, digits = 1): string {
  return v != null ? v.toFixed(digits) : '—';
}

const compLabel = computed(() => {
  const c = state.value?.compressor;
  return c != null ? c.toUpperCase() : '—';
});

const oatLabel = computed(() => {
  const oat = g3xState.value?.oatCelsius;
  return oat != null ? ((oat * 9) / 5 + 32).toFixed(0) : '—';
});
</script>

<template>
  <PanelGrid>
    <!-- Col 1–4, Row 1: Setpoint selector -->
    <PanelSelect
      :col="1"
      :row="1"
      :col-span="4"
      :row-span="1"
      :options="setpointOptions"
      :model-value="setpointValue"
      :disabled="setpointDisabled"
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

    <!-- Col 5–8, Rows 1–2: Fan speed selector -->
    <PanelSelect
      :col="5"
      :row="1"
      :col-span="4"
      :row-span="2"
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
      label="Blow"
      :model-value="fmt(state?.blowerTemp)"
    />

    <!-- Col 5–8, Row 4: Compressor status -->
    <PanelValue
      :col="5"
      :row="4"
      :col-span="4"
      label="Comp"
      :model-value="compLabel"
    />

    <!-- Col 9–12, Rows 1–2: Mode selector -->
    <PanelSelect
      :col="9"
      :row="1"
      :col-span="4"
      :row-span="2"
      :options="modeOptions"
      :model-value="state?.mode ?? 'off'"
      @update:model-value="(v) => airconSet('mode', v)"
    />

    <!-- Col 9–12, Row 3: Baggage temp -->
    <PanelValue
      :col="9"
      :row="3"
      :col-span="4"
      label="Bag"
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
      label="Exh"
      :model-value="fmt(state?.exhaustTemp)"
    />

    <!-- Col 13–16, Row 4: Outside air temp (from G3X) -->
    <PanelValue
      :col="13"
      :row="4"
      :col-span="4"
      label="OAT"
      :model-value="oatLabel"
    />
  </PanelGrid>
</template>

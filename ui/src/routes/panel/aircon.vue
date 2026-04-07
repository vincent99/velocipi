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

const { airConState } = useDeviceState();

const state = computed(() => airConState.value);
const connected = computed(() => state.value?.connected ?? false);

// ── Selectors ──────────────────────────────────────────────────────────────

const modeOptions: SelectOption[] = [
  { name: 'Off', value: 'off', icon: 'power-off' },
  { name: 'Fan', value: 'fan', icon: 'wind' },
  { name: 'Auto', value: 'auto', icon: 'temperature-low' },
  { name: 'Cool', value: 'cool', icon: 'snowflake' },
];

const fanOptions: SelectOption[] = [
  { name: 'Low', value: 'low', icon: 'minus' },
  { name: 'Med', value: 'medium', icon: 'equals' },
  { name: 'High', value: 'high', icon: 'menu-burger' },
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

// Setpoint: nudge ±0.5°F via inner knob simulation through the select.
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
  return v != null ? v.toFixed(digits) + '°' : '—';
}

const compLabel = computed(() => {
  if (!connected.value) {
    return 'N/C';
  }
  if (state.value?.compressor == null) {
    return '—';
  }
  return state.value.compressor ? 'ON' : 'OFF';
});
</script>

<template>
  <PanelGrid>
    <!-- Col 1–4: Mode selector -->
    <PanelSelect
      :col="1"
      :row="1"
      :col-span="4"
      :row-span="2"
      :options="modeOptions"
      :model-value="state?.mode ?? 'off'"
      @update:model-value="(v) => airconSet('mode', v)"
    />

    <!-- Col 1–4: Fan speed selector -->
    <PanelSelect
      :col="1"
      :row="3"
      :col-span="4"
      :row-span="2"
      :options="fanOptions"
      :model-value="state?.fan ?? 'low'"
      @update:model-value="(v) => airconSet('fan', v)"
    />

    <!-- Col 5–8: Setpoint selector -->
    <PanelSelect
      :col="5"
      :row="1"
      :col-span="4"
      :row-span="2"
      :options="setpointOptions"
      :model-value="setpointValue"
      @update:model-value="
        (v) => airconSet('setpoint', parseFloat(v).toFixed(2))
      "
    />

    <!-- Col 5–8: Current temp -->
    <PanelValue
      :col="5"
      :row="3"
      :col-span="4"
      label="Current"
      :model-value="fmt(state?.currentTemp)"
    />

    <!-- Col 5–8: Compressor on/off status -->
    <PanelValue
      :col="5"
      :row="4"
      :col-span="4"
      label="Comp"
      :model-value="compLabel"
    />

    <!-- Col 9–12: Blower + Exhaust + Baggage + Tail temps -->
    <PanelValue
      :col="9"
      :row="1"
      :col-span="4"
      label="Blower"
      :model-value="fmt(state?.blowerTemp)"
    />
    <PanelValue
      :col="9"
      :row="2"
      :col-span="4"
      label="Exhaust"
      :model-value="fmt(state?.exhaustTemp)"
    />
    <PanelValue
      :col="9"
      :row="3"
      :col-span="4"
      label="Baggage"
      :model-value="fmt(state?.baggageTemp)"
    />
    <PanelValue
      :col="9"
      :row="4"
      :col-span="4"
      label="Tail"
      :model-value="fmt(state?.tailTemp)"
    />

    <!-- Col 13–16: Panel + Comp temps, plus connection status -->
    <PanelValue
      :col="13"
      :row="1"
      :col-span="4"
      label="Panel"
      :model-value="fmt(state?.panelTemp)"
    />
    <PanelValue
      :col="13"
      :row="2"
      :col-span="4"
      label="Cabin"
      :model-value="fmt(state?.cabinTemp)"
    />
    <PanelValue
      :col="13"
      :row="3"
      :col-span="4"
      :model-value="connected ? 'BLE OK' : 'No BLE'"
      value-align="center"
    />
    <PanelValue
      :col="13"
      :row="4"
      :col-span="4"
      label="Set"
      :model-value="
        state?.setpoint != null ? state.setpoint.toFixed(0) + '°F' : '—'
      "
    />
  </PanelGrid>
</template>

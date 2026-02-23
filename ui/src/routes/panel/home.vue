<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const panelMeta: PanelMeta = {
  name: 'Home',
  icon: 'home',
  sort: -1,
};
</script>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useWebSocket } from '@/composables/useWebSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import { useCameraList } from '@/composables/useCameraList';
import { useConfig } from '@/composables/useConfig';
import { useTime, formatTz, formatUtcClock } from '@/composables/useTime';
import PanelGrid from '@/components/panel/PanelGrid.vue';
import PanelSelect from '@/components/panel/PanelSelect.vue';
import PanelValue from '@/components/panel/PanelValue.vue';
import type { SelectOption } from '@/components/panel/PanelSelect.vue';

const { send } = useWebSocket();
const { localCamera, destTimezone } = useDeviceState();
const { cameras } = useCameraList();
const { config } = useConfig();
const { now } = useTime();
const timeLabelWidth = 26;

const cameraOptions = computed<SelectOption[]>(() =>
  cameras.value.map((name) => ({
    name,
    value: name,
    icon: 'camera-viewfinder',
  }))
);

function setLocalCamera(name: string) {
  send({ type: 'setLocalCamera', camera: name });
}

// Dummy data for layout testing
const brightnessVal = ref('50');
const brightnessOptions: SelectOption[] = [
  { name: '25%', value: '25', icon: 'brightness-low' },
  { name: '50%', value: '50', icon: 'brightness' },
  { name: '75%', value: '75', icon: 'brightness' },
  { name: '100%', value: '100', icon: 'sun' },
];

const modeVal = ref('day');
const modeOptions: SelectOption[] = [
  { name: 'Day', value: 'day', icon: 'sun' },
  { name: 'Night', value: 'night', icon: 'moon' },
  { name: 'Auto', value: 'auto', icon: 'eclipse-alt' },
];

const volumeVal = ref('med');
const volumeOptions: SelectOption[] = [
  { name: 'Off', value: 'off' },
  { name: 'Low', value: 'low' },
  { name: 'Med', value: 'med' },
  { name: 'High', value: 'high' },
];

// Clock computeds — recompute whenever `now` ticks.
const timeFormat = computed(() => config.value?.panel.timeFormat ?? '12h');
const homeTimezone = computed(
  () => config.value?.panel.homeTimezone ?? 'America/Phoenix'
);
const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone;

const localTime = computed(() =>
  formatTz(now.value, localTz, timeFormat.value, false)
);
const homeTime = computed(() =>
  formatTz(now.value, homeTimezone.value, timeFormat.value, false)
);
const destTime = computed(() =>
  formatTz(now.value, destTimezone.value, timeFormat.value, false)
);
const utcTime = computed(() => formatUtcClock(now.value));
</script>

<template>
  <PanelGrid>
    <!-- Camera select: columns 1-4, all 4 rows -->
    <PanelSelect
      :col="1"
      :row="1"
      :col-span="4"
      :row-span="4"
      :options="cameraOptions"
      :model-value="localCamera"
      @update:model-value="setLocalCamera"
    />

    <!-- Brightness: columns 5-8, rows 1-2 (2-row tall) -->
    <PanelSelect
      v-model="brightnessVal"
      :col="5"
      :row="1"
      :col-span="4"
      :row-span="2"
      :options="brightnessOptions"
    />

    <!-- Mode: columns 5-8, rows 3-4 (2-row tall) -->
    <PanelSelect
      v-model="modeVal"
      :col="5"
      :row="3"
      :col-span="4"
      :row-span="2"
      :options="modeOptions"
    />

    <!-- Volume: columns 9-11, rows 1 (1-row) -->
    <PanelSelect
      v-model="volumeVal"
      :col="9"
      :row="1"
      :col-span="3"
      :row-span="1"
      :options="volumeOptions"
    />

    <!-- Mode dummy 3-row: columns 9-11, rows 2-4 -->
    <PanelSelect
      v-model="modeVal"
      :col="9"
      :row="2"
      :col-span="3"
      :row-span="3"
      :options="modeOptions"
    />

    <!-- Clocks: columns 12-16 (5 wide), one row each -->
    <PanelValue
      :col="12"
      :row="1"
      :col-span="5"
      label="Local"
      :model-value="localTime"
      value-align="left"
      :min-label-width="timeLabelWidth"
    />
    <PanelValue
      :col="12"
      :row="2"
      :col-span="5"
      label="Home"
      :model-value="homeTime"
      value-align="left"
      :min-label-width="timeLabelWidth"
    />
    <PanelValue
      :col="12"
      :row="3"
      :col-span="5"
      label="Dest"
      :model-value="destTime"
      value-align="left"
      :min-label-width="timeLabelWidth"
    />
    <PanelValue
      :col="12"
      :row="4"
      :col-span="5"
      label="UTC"
      :model-value="utcTime"
      value-align="left"
      :min-label-width="timeLabelWidth"
    />
  </PanelGrid>
</template>

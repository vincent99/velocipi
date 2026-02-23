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
import PanelGrid from '@/components/panel/PanelGrid.vue';
import PanelSelect from '@/components/panel/PanelSelect.vue';
import type { SelectOption } from '@/components/panel/PanelSelect.vue';

const { send } = useWebSocket();
const { localCamera } = useDeviceState();
const { cameras } = useCameraList();

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

    <!-- Volume: columns 9-12, rows 1-1 (1-row) -->
    <PanelSelect
      v-model="volumeVal"
      :col="9"
      :row="1"
      :col-span="4"
      :row-span="1"
      :options="volumeOptions"
    />

    <!-- Volume again as 4-row: columns 13-16, all 4 rows -->
    <PanelSelect
      v-model="modeVal"
      :col="13"
      :row="1"
      :col-span="4"
      :row-span="4"
      :options="modeOptions"
    />
  </PanelGrid>
</template>

<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const panelMeta: PanelMeta = {
  name: 'Cameras',
  icon: 'camera-viewfinder',
  sort: -1,
};
</script>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue';
import { useWebSocket } from '@/composables/useWebSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import { useCameraList } from '@/composables/useCameraList';
import type { LogicalKey } from '@/types/ws';
import PanelGrid from '@/components/panel/PanelGrid.vue';
import PanelSelect from '@/components/panel/PanelSelect.vue';
import PanelValue from '@/components/panel/PanelValue.vue';
import PanelProgressBar from '@/components/panel/PanelProgressBar.vue';
import type { SelectOption } from '@/components/panel/PanelSelect.vue';

const { send } = useWebSocket();
const { localCamera, dvrState, diskSpace, siyiAttitude } = useDeviceState();
const { cameraList } = useCameraList();

// Camera selector options
const cameraOptions = computed<SelectOption[]>(() =>
  cameraList.value.map((c) => ({
    name: c.name,
    value: c.name,
    icon: 'camera-viewfinder',
  }))
);

// Determine active camera driver
const activeDriver = computed(() => {
  const cam = cameraList.value.find((c) => c.name === localCamera.value);
  return cam?.driver ?? 'rtsp';
});

// Siyi: current attitude for active camera
const activeSiyiAttitude = computed(
  () => siyiAttitude.get(localCamera.value) ?? null
);

// Siyi mode select
const siyiModeOptions: SelectOption[] = [
  { name: 'Lock', value: 'lock', icon: 'lock' },
  { name: 'Follow', value: 'follow', icon: 'refresh' },
  { name: 'FPV', value: 'fpv', icon: 'plane' },
];

// DVR state options
const dvrStateOptions: SelectOption[] = [
  { name: 'Recording', value: 'on', icon: 'record' },
  { name: 'Paused', value: 'paused', icon: 'pause' },
];
const dvrStateValue = computed(() => dvrState.value ?? 'on');

// Disk bar
const diskPct = computed(() => diskSpace.value?.usedPct ?? 0);
const diskFreeLabel = computed(() => {
  if (!diskSpace.value) {
    return '— GB Free';
  }
  return `${diskSpace.value.freeGB.toFixed(1)} GB Free`;
});
const diskBarLabel = computed(() => `${Math.round(diskPct.value)}%`);

// Siyi API helpers
function siyiPost(action: string, body: Record<string, unknown> = {}) {
  const cam = localCamera.value;
  if (!cam) {
    return;
  }
  fetch(`/siyi/${encodeURIComponent(cam)}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).catch(() => {});
}

function setSiyiMode(mode: string) {
  siyiPost('mode', { mode });
}

function setDvrState(state: string) {
  fetch('/dvr/state', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state }),
  }).catch(() => {});
}

// Joystick key handling — capture phase so we intercept before layout handlers.
const RATE = 70; // gimbal rate -100..+100

const heldKeys: Partial<Record<LogicalKey, boolean>> = {};

function sendGimbalFromKeys() {
  const yaw = heldKeys['joy-left'] ? -RATE : heldKeys['joy-right'] ? RATE : 0;
  const pitch = heldKeys['joy-up'] ? RATE : heldKeys['joy-down'] ? -RATE : 0;
  siyiPost('gimbal', { yaw, pitch });
}

function handleKeydown(e: Event) {
  const key = (e as KeyboardEvent & { logicalKey?: LogicalKey }).logicalKey;
  if (!key) {
    return;
  }
  if (activeDriver.value === 'siyi') {
    if (
      key === 'joy-left' ||
      key === 'joy-right' ||
      key === 'joy-up' ||
      key === 'joy-down'
    ) {
      if (!heldKeys[key]) {
        heldKeys[key] = true;
        sendGimbalFromKeys();
      }
      e.stopPropagation();
    } else if (key === 'inner-left') {
      siyiPost('zoom', { direction: -1 });
      e.stopPropagation();
    } else if (key === 'inner-right') {
      siyiPost('zoom', { direction: 1 });
      e.stopPropagation();
    }
  }
}

function handleKeyup(e: Event) {
  const key = (e as KeyboardEvent & { logicalKey?: LogicalKey }).logicalKey;
  if (!key) {
    return;
  }
  if (activeDriver.value === 'siyi') {
    if (
      key === 'joy-left' ||
      key === 'joy-right' ||
      key === 'joy-up' ||
      key === 'joy-down'
    ) {
      heldKeys[key] = false;
      sendGimbalFromKeys();
      e.stopPropagation();
    } else if (key === 'inner-left' || key === 'inner-right') {
      siyiPost('zoom', { direction: 0 });
      e.stopPropagation();
    }
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown, true);
  document.addEventListener('keyup', handleKeyup, true);
});
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown, true);
  document.removeEventListener('keyup', handleKeyup, true);
});
</script>

<template>
  <PanelGrid>
    <!-- Camera selector: cols 1–4, all 4 rows -->
    <PanelSelect
      :col="1"
      :row="1"
      :col-span="4"
      :row-span="4"
      :options="cameraOptions"
      :model-value="localCamera"
      @update:model-value="(v) => send({ type: 'setLocalCamera', camera: v })"
    />

    <!-- Siyi controls: cols 5–12, rows 1–4 (only when driver === 'siyi') -->
    <template v-if="activeDriver === 'siyi'">
      <!-- Row 1, cols 5–8: Follow mode -->
      <PanelSelect
        :col="5"
        :row="1"
        :col-span="4"
        :row-span="1"
        :options="siyiModeOptions"
        model-value="follow"
        @update:model-value="setSiyiMode"
      />
      <!-- Row 2, cols 5–8: Auto-focus -->
      <PanelSelect
        :col="5"
        :row="2"
        :col-span="4"
        :row-span="1"
        :options="[{ name: 'Auto Focus', value: 'af', icon: 'aperture' }]"
        model-value="af"
        @update:model-value="() => siyiPost('focus', { mode: 'auto' })"
      />
      <!-- Row 3, cols 5–8: Center -->
      <PanelSelect
        :col="5"
        :row="3"
        :col-span="4"
        :row-span="1"
        :options="[{ name: 'Center', value: 'center', icon: 'target' }]"
        model-value="center"
        @update:model-value="() => siyiPost('center')"
      />
      <!-- Row 4, cols 5–8: Photo / Video -->
      <PanelSelect
        :col="5"
        :row="4"
        :col-span="4"
        :row-span="1"
        :options="[
          { name: 'Take Photo', value: 'photo', icon: 'camera' },
          { name: 'Rec Video', value: 'video', icon: 'record' },
        ]"
        model-value="photo"
        @update:model-value="(v) => siyiPost(v === 'video' ? 'video' : 'photo')"
      />

      <!-- Attitude values: cols 9–12, rows 1–4 -->
      <PanelValue
        :col="9"
        :row="1"
        :col-span="4"
        label="Yaw"
        :model-value="
          activeSiyiAttitude
            ? activeSiyiAttitude.yaw.toFixed(1) + '\u00b0'
            : '\u2014'
        "
      />
      <PanelValue
        :col="9"
        :row="2"
        :col-span="4"
        label="Pitch"
        :model-value="
          activeSiyiAttitude
            ? activeSiyiAttitude.pitch.toFixed(1) + '\u00b0'
            : '\u2014'
        "
      />
      <PanelValue
        :col="9"
        :row="3"
        :col-span="4"
        label="Roll"
        :model-value="
          activeSiyiAttitude
            ? activeSiyiAttitude.roll.toFixed(1) + '\u00b0'
            : '\u2014'
        "
      />
      <PanelValue
        :col="9"
        :row="4"
        :col-span="4"
        label="Yaw/s"
        :model-value="
          activeSiyiAttitude
            ? activeSiyiAttitude.yawRate.toFixed(1) + '\u00b0/s'
            : '\u2014'
        "
      />
    </template>

    <!-- DVR / Disk: cols 13–16, always shown -->
    <!-- Rows 1–2: DVR state toggle or Off label -->
    <PanelValue
      v-if="dvrState === 'off'"
      :col="13"
      :row="1"
      :col-span="4"
      :row-span="2"
      model-value="DVR Off"
      value-align="center"
    />
    <PanelSelect
      v-else
      :col="13"
      :row="1"
      :col-span="4"
      :row-span="2"
      :options="dvrStateOptions"
      :model-value="dvrStateValue"
      @update:model-value="setDvrState"
    />

    <!-- Row 3: disk usage bar -->
    <PanelProgressBar
      :col="13"
      :row="3"
      :col-span="4"
      :value="diskPct"
      :warn-at="80"
      :crit-at="95"
      :label="diskBarLabel"
    />

    <!-- Row 4: disk free label -->
    <PanelValue
      :col="13"
      :row="4"
      :col-span="4"
      :model-value="diskFreeLabel"
      value-align="center"
    />
  </PanelGrid>
</template>

<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Settings',
  icon: 'settings-sliders',
  sort: 99,
};
</script>

<script setup lang="ts">
import { ref, provide, onMounted } from 'vue';
import type { FullConfig, FullConfigResponse } from '@/types/config';
import SettingsField from '@/components/settings/SettingsField.vue';
import { settingsKey } from '@/components/settings/settingsContext';
import SettingsGroup from '@/components/settings/SettingsGroup.vue';

const cfg = ref<FullConfig | null>(null);
const defaults = ref<FullConfig | null>(null);
const saving = ref(false);
const saved = ref(false);
const error = ref('');

onMounted(async () => {
  try {
    const r = await fetch('/config?full=true');
    if (!r.ok) {
      throw new Error(await r.text());
    }
    const data: FullConfigResponse = await r.json();
    cfg.value = data.config;
    defaults.value = data.defaults;
  } catch (e: unknown) {
    error.value = 'Failed to load config: ' + String(e);
  }
});

async function save() {
  if (!cfg.value) {
    return;
  }
  saving.value = true;
  error.value = '';
  saved.value = false;
  try {
    const r = await fetch('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg.value),
    });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    saved.value = true;
    setTimeout(() => {
      saved.value = false;
    }, 4000);
  } catch (e: unknown) {
    error.value = 'Save failed: ' + String(e);
  } finally {
    saving.value = false;
  }
}

function getPath(path: string): unknown {
  return path.split('.').reduce((o: any, k) => o?.[k], cfg.value);
}
function setPath(path: string, value: unknown) {
  const keys = path.split('.');
  const last = keys.pop()!;
  (keys.reduce((o: any, k) => o[k], cfg.value!) as any)[last] = value;
}
function isModified(path: string): boolean {
  return (
    JSON.stringify(getPath(path)) !==
    JSON.stringify(
      path.split('.').reduce((o: any, k) => o?.[k], defaults.value)
    )
  );
}
function reset(path: string) {
  const defVal = path.split('.').reduce((o: any, k) => o?.[k], defaults.value);
  setPath(path, structuredClone(defVal));
}

provide(settingsKey, { isModified, reset, getPath, setPath });

const keyMapFields = [
  { key: 'ui.keyMap.up', label: 'Up' },
  { key: 'ui.keyMap.down', label: 'Down' },
  { key: 'ui.keyMap.left', label: 'Left' },
  { key: 'ui.keyMap.right', label: 'Right' },
  { key: 'ui.keyMap.enter', label: 'Enter' },
  { key: 'ui.keyMap.joyLeft', label: 'Joy left' },
  { key: 'ui.keyMap.joyRight', label: 'Joy right' },
  { key: 'ui.keyMap.innerLeft', label: 'Inner left' },
  { key: 'ui.keyMap.innerRight', label: 'Inner right' },
  { key: 'ui.keyMap.outerLeft', label: 'Outer left' },
  { key: 'ui.keyMap.outerRight', label: 'Outer right' },
];

const expanderBitFields = [
  { key: 'expander.bits.knobCenter', label: 'Knob center' },
  { key: 'expander.bits.knobInner', label: 'Knob inner (A)' },
  { key: 'expander.bits.knobOuter', label: 'Knob outer (A)' },
  { key: 'expander.bits.led', label: 'LED' },
  { key: 'expander.bits.joyCenter', label: 'Joy center' },
  { key: 'expander.bits.joyDown', label: 'Joy down' },
  { key: 'expander.bits.joyUp', label: 'Joy up' },
  { key: 'expander.bits.joyRight', label: 'Joy right' },
  { key: 'expander.bits.joyLeft', label: 'Joy left' },
  { key: 'expander.bits.joyKnob', label: 'Joy knob (A)' },
];
</script>

<template>
  <div class="settings-page">
    <div v-if="!cfg && !error" class="loading">Loading…</div>
    <div v-if="error" class="error-banner">
      {{ error }}
    </div>

    <form v-if="cfg && defaults" @submit.prevent="save">
      <!-- Server -->
      <section>
        <h2>Server</h2>
        <SettingsField
          label="Listen address"
          path="addr"
          placeholder="0.0.0.0:8080"
        />
        <SettingsField
          label="App URL"
          path="appUrl"
          placeholder="http://localhost:8081/panel/"
        />
        <SettingsField
          label="I²C device"
          path="i2cDevice"
          placeholder="/dev/i2c-1"
        />
        <SettingsField
          label="Ping interval"
          path="pingInterval"
          placeholder="1s"
        />
      </section>

      <!-- Display -->
      <section>
        <h2>Display</h2>
        <SettingsGroup title="OLED">
          <SettingsField
            label="SPI port"
            path="oled.spiPort"
            placeholder="/dev/spidev0.0"
          />
          <SettingsField
            label="SPI speed"
            path="oled.spiSpeed"
            placeholder="2.40MHz"
          />
          <SettingsField
            label="GPIO chip"
            path="oled.gpioChip"
            placeholder="gpiochip0"
          />
          <SettingsField
            label="DC pin"
            path="oled.dcPin"
            type="number"
            :min="0"
          />
          <SettingsField
            label="Reset pin"
            path="oled.resetPin"
            type="number"
            :min="0"
          />
          <SettingsField
            label="Flip display"
            path="oled.flip"
            type="checkbox"
          />
        </SettingsGroup>
        <SettingsGroup title="Screen">
          <SettingsField
            label="FPS"
            path="screen.fps"
            type="number"
            :min="1"
            :max="60"
          />
          <SettingsField
            label="Splash image"
            path="screen.splashImage"
            placeholder="ui/public/img/logo.png"
          />
          <SettingsField
            label="Splash duration"
            path="screen.splashDuration"
            placeholder="2s"
          />
        </SettingsGroup>
      </section>

      <!-- UI -->
      <section>
        <h2>UI</h2>
        <SettingsField
          label="Tail number"
          path="ui.tail"
          placeholder="N711ME"
        />
        <SettingsField
          label="Header color"
          path="ui.headerColor"
          type="color"
          placeholder="#3b82f6"
        />
        <SettingsGroup title="Panel">
          <SettingsField
            label="Width (px)"
            path="ui.panel.width"
            type="number"
            :min="1"
          />
          <SettingsField
            label="Height (px)"
            path="ui.panel.height"
            type="number"
            :min="1"
          />
        </SettingsGroup>
        <SettingsGroup title="Nav menu">
          <SettingsField
            label="Hide delay (ms)"
            path="ui.navMenu.hideDelay"
            type="number"
            :min="0"
          />
          <SettingsField
            label="Cell width (px)"
            path="ui.navMenu.cellWidth"
            type="number"
            :min="1"
          />
        </SettingsGroup>
        <SettingsGroup title="Key map" :columns="2">
          <SettingsField
            v-for="f in keyMapFields"
            :key="f.key"
            :label="f.label"
            :path="f.key"
          />
        </SettingsGroup>
      </section>

      <!-- Hardware -->
      <section>
        <h2>Hardware</h2>
        <SettingsGroup title="Air sensor (BME280)">
          <SettingsField
            label="I²C address"
            path="airSensor.address"
            type="number"
            :min="0"
            :max="127"
          />
          <SettingsField
            label="Poll interval"
            path="airSensor.interval"
            placeholder="1s"
          />
        </SettingsGroup>
        <SettingsGroup title="Light sensor (VEML6030)">
          <SettingsField
            label="I²C address"
            path="lightSensor.address"
            type="number"
            :min="0"
            :max="127"
          />
          <SettingsField
            label="Poll interval"
            path="lightSensor.interval"
            placeholder="1s"
          />
        </SettingsGroup>
        <SettingsGroup title="Expander (SX1509)">
          <SettingsField
            label="I²C address"
            path="expander.address"
            type="number"
            :min="0"
            :max="127"
          />
          <SettingsField
            label="Poll interval"
            path="expander.interval"
            placeholder="2ms"
          />
        </SettingsGroup>
        <SettingsGroup title="Expander bit assignments" :columns="2">
          <SettingsField
            v-for="f in expanderBitFields"
            :key="f.key"
            :label="f.label"
            :path="f.key"
            type="number"
            :min="0"
            :max="15"
          />
        </SettingsGroup>
      </section>

      <!-- Tires -->
      <section>
        <h2>TPMS sensors</h2>
        <p class="hint">One Bluetooth address per line.</p>

        <SettingsGroup
          v-for="pos in ['nose', 'left', 'right'] as const"
          :key="pos"
          :title="pos"
        >
          <template #header-action>
            <button
              v-if="isModified('tires.' + pos)"
              type="button"
              class="group-reset"
              title="Reset to default"
              @click="reset('tires.' + pos)"
            >
              <i class="fi-sr-rotate-left" />
            </button>
          </template>
          <textarea
            :value="(cfg.tires[pos] as string[]).join('\n')"
            :class="{ modified: isModified('tires.' + pos) }"
            rows="2"
            placeholder="4a:xx:xx:xx:xx:xx"
            @input="
              (cfg!.tires[pos] as string[]) = (
                $event.target as HTMLTextAreaElement
              ).value
                .split('\n')
                .map((s) => s.trim())
                .filter(Boolean)
            "
          />
        </SettingsGroup>
      </section>

      <!-- Save -->
      <div class="save-bar">
        <span v-if="saved" class="saved-msg"
          >Saved — restart the server to apply changes.</span
        >
        <span v-if="error" class="error-msg">{{ error }}</span>
        <button type="submit" :disabled="saving">
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped lang="scss">
.settings-page {
  max-width: 600px;
  margin: 0 auto;
  padding: 1.5rem 1rem 2rem;
  color: #e0e0e0;
  font-size: 0.9rem;
}

.loading {
  color: #888;
  padding: 2rem 0;
}

.error-banner {
  background: #5a1a1a;
  border: 1px solid #a33;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 1.5rem;
  color: #f88;
}

section {
  margin-bottom: 2rem;

  h2 {
    font-size: 1rem;
    font-weight: 600;
    color: #fff;
    border-bottom: 1px solid #333;
    padding-bottom: 0.4rem;
    margin: 0 0 1rem;
  }
}

.hint {
  color: #666;
  font-size: 0.8rem;
  margin: 0 0 0.75rem;
}

.group-reset {
  background: none;
  border: none;
  color: #3b82f6;
  cursor: pointer;
  padding: 0;
  font-size: 0.8rem;
  display: flex;
  align-items: center;

  &:hover {
    color: #60a5fa;
  }
}

textarea {
  width: 100%;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.8rem;
  font-family: monospace;
  resize: vertical;
  box-sizing: border-box;

  &:focus {
    outline: none;
    border-color: #666;
  }
  &.modified {
    border-color: #3b82f6;
  }
}

.save-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding-top: 0.5rem;

  button {
    margin-left: auto;
    background: #3b82f6;
    border: none;
    border-radius: 6px;
    color: #fff;
    padding: 0.45rem 1.25rem;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.1s;

    &:hover:not(:disabled) {
      background: #2563eb;
    }
    &:disabled {
      opacity: 0.5;
      cursor: default;
    }
  }
}

.saved-msg {
  color: #4ade80;
  font-size: 0.85rem;
}
.error-msg {
  color: #f87171;
  font-size: 0.85rem;
}
</style>

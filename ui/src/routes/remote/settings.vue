<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Settings',
  icon: 'settings-sliders',
  sort: 99,
  admin: true,
};
</script>

<script setup lang="ts">
import { ref, provide, computed, onMounted } from 'vue';
import type { FullConfig, FullConfigResponse } from '@/types/config';
import SettingsField from '@/components/settings/SettingsField.vue';
import { settingsKey } from '@/components/settings/settingsContext';
import SettingsGroup from '@/components/settings/SettingsGroup.vue';

const cfg = ref<FullConfig | null>(null);
const defaults = ref<FullConfig | null>(null);
const saving = ref(false);
const saved = ref(false);
const error = ref('');

// AirCon BLE settings — loaded from /aircon/state, not from the YAML config.
const acSettings = ref<Record<string, { value: number; default: number }> | null>(null);
const acEdits = ref<Record<string, number>>({});
const activeSection = ref('filesystem');

interface AudioDevice {
  id: string;
  name: string;
}
const audioDevices = ref<AudioDevice[]>([]);

onMounted(async () => {
  try {
    const [cfgRes, devRes] = await Promise.all([
      fetch('/config?full=true'),
      fetch('/music/audio-devices'),
    ]);
    if (!cfgRes.ok) {
      throw new Error(await cfgRes.text());
    }
    const data: FullConfigResponse = await cfgRes.json();
    cfg.value = data.config;
    defaults.value = data.defaults;
    if (devRes.ok) {
      audioDevices.value = await devRes.json();
    }
  } catch (e: unknown) {
    error.value = 'Failed to load config: ' + String(e);
  }
  try {
    const acRes = await fetch('/aircon/state');
    if (acRes.ok) {
      const acData = await acRes.json();
      acSettings.value = acData.state?.settings ?? null;
    }
  } catch {
    // aircon may not be configured — silently ignore
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
    if (Object.keys(acEdits.value).length > 0 && acSettings.value) {
      const r2 = await fetch('/aircon/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ field: 'settings', value: JSON.stringify(acEdits.value) }),
      });
      if (r2.ok) {
        acEdits.value = {};
      }
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

// ── AirCon BLE settings helpers ───────────────────────────────────────────────

const acSettingsFields = [
  { key: 'delta',               label: 'Auto delta (°F)',         min: 0.5, step: 0.5 },
  { key: 'fan_high_thresh',     label: 'Fan high threshold (°F)', min: 0.5, step: 0.5 },
  { key: 'fan_med_thresh',      label: 'Fan med threshold (°F)',  min: 0.5, step: 0.5 },
  { key: 'fan_change_interval', label: 'Fan change interval (s)', min: 1,   step: 1   },
  { key: 'auto_loop_interval',  label: 'Auto loop interval (s)',  min: 1,   step: 1   },
  { key: 'temp_read_interval',  label: 'Temp read interval (s)',  min: 1,   step: 1   },
];

function acValue(key: string): number {
  return key in acEdits.value ? acEdits.value[key] : (acSettings.value?.[key]?.value ?? 0);
}
function acIsModified(key: string): boolean {
  const def = acSettings.value?.[key]?.default;
  return def !== undefined && acValue(key) !== def;
}
function acReset(key: string) {
  const def = acSettings.value?.[key]?.default;
  if (def !== undefined) {
    acEdits.value = { ...acEdits.value, [key]: def };
  }
}
function acSet(key: string, v: number) {
  acEdits.value = { ...acEdits.value, [key]: v };
}

// AcoustID score is stored as 0.0–1.0 but presented as 0–100 percent.
const acoustidScorePct = computed({
  get: () =>
    cfg.value ? Math.round(cfg.value.music.acoustidMinScore * 100) : 0,
  set: (pct: number) => {
    if (cfg.value) {
      cfg.value.music.acoustidMinScore = pct / 100;
    }
  },
});

// I2C address displayed as hex.
function getHex(path: string): string {
  const v = getPath(path);
  return typeof v === 'number' ? '0x' + v.toString(16).padStart(2, '0') : '';
}
function setHex(path: string, raw: string) {
  const n = parseInt(raw, 16);
  if (!isNaN(n)) {
    setPath(path, n);
  }
}

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

const sections = [
  { id: 'filesystem', label: 'Filesystem' },
  { id: 'server', label: 'Server' },
  { id: 'ui', label: 'UI' },
  { id: 'hardware', label: 'Hardware' },
  { id: 'dvr', label: 'DVR' },
  { id: 'music', label: 'Music' },
];
</script>

<template>
  <div class="settings-page">
    <div v-if="!cfg && !error" class="loading">Loading…</div>
    <div v-if="error" class="error-banner">{{ error }}</div>

    <form v-if="cfg && defaults" class="settings-layout" @submit.prevent="save">
      <!-- Left nav -->
      <nav class="settings-nav">
        <button
          v-for="s in sections"
          :key="s.id"
          type="button"
          class="nav-item"
          :class="{ 'nav-item--active': activeSection === s.id }"
          @click="activeSection = s.id"
        >
          {{ s.label }}
        </button>

        <div class="nav-spacer" />

        <span v-if="saved" class="saved-msg">Saved ✓</span>
        <span v-if="error" class="error-msg">{{ error }}</span>
        <button type="submit" class="save-btn" :disabled="saving">
          {{ saving ? 'Saving…' : 'Save All' }}
        </button>
      </nav>

      <!-- Right content -->
      <div class="settings-content">
        <!-- Filesystem -->
        <section v-if="activeSection === 'filesystem'">
          <h2>Filesystem</h2>
          <SettingsField
            label="Music directory"
            path="music.musicDir"
            placeholder="music"
          />
          <SettingsField
            label="Recordings directory"
            path="dvr.recordingsDir"
            placeholder="recordings"
          />
          <SettingsField
            label="Backup directory"
            path="music.backupDir"
            placeholder="backup"
          />
        </section>

        <!-- Server -->
        <section v-if="activeSection === 'server'">
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
            label="SPI device"
            path="spiDevice"
            placeholder="/dev/spidev0.0"
          />
          <SettingsField
            label="SPI speed"
            path="oled.spiSpeed"
            placeholder="2.40MHz"
          />
          <SettingsField
            label="Ping interval"
            path="pingInterval"
            placeholder="1s"
          />
        </section>

        <!-- UI -->
        <section v-if="activeSection === 'ui'">
          <h2>UI</h2>
          <SettingsGroup title="Theme">
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
            <SettingsField
              label="Admin header color"
              path="ui.adminHeaderColor"
              type="color"
              placeholder="#dc2626"
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
            <SettingsField
              label="Control background"
              path="ui.panel.controlBackground"
              type="color"
            />
            <SettingsField
              label="Control border"
              path="ui.panel.controlBorder"
              type="color"
            />
            <SettingsField
              label="Control text"
              path="ui.panel.controlText"
              type="color"
            />
            <SettingsField
              label="Selected background"
              path="ui.panel.selectedBackground"
              type="color"
            />
            <SettingsField
              label="Selected border"
              path="ui.panel.selectedBorder"
              type="color"
            />
            <SettingsField
              label="Selected text"
              path="ui.panel.selectedText"
              type="color"
            />
            <SettingsField
              label="Active background"
              path="ui.panel.activeBackground"
              type="color"
            />
            <SettingsField
              label="Active border"
              path="ui.panel.activeBorder"
              type="color"
            />
            <SettingsField
              label="Active text"
              path="ui.panel.activeText"
              type="color"
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
            <SettingsField
              label="Long-press (ms)"
              path="ui.navMenu.longPressMs"
              type="number"
              :min="0"
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
        <section v-if="activeSection === 'hardware'">
          <h2>Hardware</h2>
          <SettingsGroup title="OLED display">
            <SettingsField
              label="Driver"
              path="oled.driver"
              placeholder="ssd1327"
            />
            <SettingsField
              label="GPIO chip"
              path="oled.gpioChip"
              placeholder="gpiochip0"
            />
            <SettingsField
              label="Status pin"
              path="oled.statusPin"
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
              label="Flip display 180°"
              path="oled.flip"
              type="checkbox"
            />
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
            <SettingsField
              label="FPS"
              path="screen.fps"
              type="number"
              :min="1"
              :max="60"
            />
          </SettingsGroup>
          <SettingsGroup title="Expander (SX1509)">
            <div
              class="sf-row"
              :class="{ modified: isModified('expander.address') }"
            >
              <button
                v-if="isModified('expander.address')"
                type="button"
                class="sf-reset"
                title="Reset to default"
                @click="reset('expander.address')"
              >
                <i class="fi-sr-rotate-left" />
              </button>
              <span v-else class="sf-reset-placeholder" />
              <label class="sf-label">I²C address</label>
              <input
                class="sf-input"
                :value="getHex('expander.address')"
                placeholder="0x20"
                @change="
                  setHex(
                    'expander.address',
                    ($event.target as HTMLInputElement).value
                  )
                "
              />
            </div>
            <SettingsField
              label="Poll interval"
              path="expander.interval"
              placeholder="2ms"
            />
            <SettingsGroup title="Pin assignments">
              <div class="bit-grid">
                <div
                  v-for="f in expanderBitFields"
                  :key="f.key"
                  class="sf-row"
                  :class="{ modified: isModified(f.key) }"
                >
                  <button
                    v-if="isModified(f.key)"
                    type="button"
                    class="sf-reset"
                    title="Reset to default"
                    @click="reset(f.key)"
                  >
                    <i class="fi-sr-rotate-left" />
                  </button>
                  <span v-else class="sf-reset-placeholder" />
                  <label class="sf-label">{{ f.label }}</label>
                  <input
                    class="sf-input"
                    type="number"
                    min="0"
                    max="15"
                    :value="getPath(f.key) as number"
                    @change="
                      setPath(
                        f.key,
                        Number(($event.target as HTMLInputElement).value)
                      )
                    "
                  />
                </div>
              </div>
            </SettingsGroup>
          </SettingsGroup>
          <SettingsGroup title="Air sensor (BME280)">
            <div
              class="sf-row"
              :class="{ modified: isModified('airSensor.address') }"
            >
              <button
                v-if="isModified('airSensor.address')"
                type="button"
                class="sf-reset"
                title="Reset to default"
                @click="reset('airSensor.address')"
              >
                <i class="fi-sr-rotate-left" />
              </button>
              <span v-else class="sf-reset-placeholder" />
              <label class="sf-label">I²C address</label>
              <input
                class="sf-input"
                :value="getHex('airSensor.address')"
                placeholder="0x77"
                @change="
                  setHex(
                    'airSensor.address',
                    ($event.target as HTMLInputElement).value
                  )
                "
              />
            </div>
            <SettingsField
              label="Poll interval"
              path="airSensor.interval"
              placeholder="1s"
            />
          </SettingsGroup>
          <SettingsGroup title="Light sensor (VEML6030)">
            <div
              class="sf-row"
              :class="{ modified: isModified('lightSensor.address') }"
            >
              <button
                v-if="isModified('lightSensor.address')"
                type="button"
                class="sf-reset"
                title="Reset to default"
                @click="reset('lightSensor.address')"
              >
                <i class="fi-sr-rotate-left" />
              </button>
              <span v-else class="sf-reset-placeholder" />
              <label class="sf-label">I²C address</label>
              <input
                class="sf-input"
                :value="getHex('lightSensor.address')"
                placeholder="0x48"
                @change="
                  setHex(
                    'lightSensor.address',
                    ($event.target as HTMLInputElement).value
                  )
                "
              />
            </div>
            <SettingsField
              label="Poll interval"
              path="lightSensor.interval"
              placeholder="1s"
            />
          </SettingsGroup>
          <SettingsGroup title="TPMS sensors">
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
          </SettingsGroup>
          <SettingsGroup title="Air Conditioner">
            <SettingsField
              label="BLE device name"
              path="airCon.deviceName"
              type="text"
            />
            <template v-if="acSettings">
              <div
                v-for="f in acSettingsFields"
                :key="f.key"
                class="sf-row"
                :class="{ modified: acIsModified(f.key) }"
              >
                <button
                  v-if="acIsModified(f.key)"
                  type="button"
                  class="sf-reset"
                  title="Reset to default"
                  @click="acReset(f.key)"
                >
                  <i class="fi-sr-rotate-left" />
                </button>
                <span v-else class="sf-reset-placeholder" />
                <label class="sf-label">{{ f.label }}</label>
                <input
                  class="sf-input"
                  type="number"
                  :min="f.min"
                  :step="f.step"
                  :value="acValue(f.key)"
                  @change="acSet(f.key, Number(($event.target as HTMLInputElement).value))"
                />
              </div>
            </template>
            <p v-else class="hint">Not connected — runtime settings unavailable.</p>
          </SettingsGroup>
        </section>

        <!-- DVR -->
        <section v-if="activeSection === 'dvr'">
          <h2>DVR</h2>
          <SettingsGroup title="Recording">
            <SettingsField
              label="Segment duration (s)"
              path="dvr.segmentDuration"
              type="number"
              :min="10"
            />
            <SettingsField
              label="Thumbnail height (px)"
              path="dvr.thumbnailHeight"
              type="number"
              :min="60"
            />
            <SettingsField
              label="Log ffmpeg output"
              path="dvr.ffmpegLog"
              type="checkbox"
            />
          </SettingsGroup>

          <div class="cameras-header">
            <h3 class="cameras-title">Cameras</h3>
            <button
              type="button"
              class="add-camera-btn"
              @click="
                cfg!.dvr.cameras.push({
                  name: '',
                  host: '',
                  port: 554,
                  username: '',
                  password: '',
                  audio: false,
                  record: undefined,
                  sort: undefined,
                })
              "
            >
              + Add camera
            </button>
          </div>
          <div
            v-for="(cam, idx) in cfg!.dvr.cameras"
            :key="idx"
            class="camera-card"
          >
            <div class="camera-card-header">
              <span class="camera-num">Camera {{ idx + 1 }}</span>
              <button
                type="button"
                class="remove-camera-btn"
                title="Remove camera"
                @click="cfg!.dvr.cameras.splice(idx, 1)"
              >
                <i class="fi-sr-trash" />
              </button>
            </div>
            <div class="camera-fields">
              <label
                >Name<input v-model="cam.name" placeholder="Front"
              /></label>
              <label
                >Host<input v-model="cam.host" placeholder="192.168.1.100"
              /></label>
              <label
                >Port<input
                  v-model.number="cam.port"
                  type="number"
                  min="1"
                  max="65535"
                  placeholder="554"
              /></label>
              <label
                >Sort<input
                  v-model.number="cam.sort"
                  type="number"
                  min="0"
                  placeholder="(optional)"
              /></label>
              <label class="audio-label"
                ><span>Audio</span
                ><input v-model="cam.audio" type="checkbox" class="audio-check"
              /></label>
              <label class="audio-label"
                ><span>Record</span
                ><input
                  :checked="cam.record !== false"
                  type="checkbox"
                  class="audio-check"
                  @change="
                    cam.record = ($event.target as HTMLInputElement).checked
                      ? undefined
                      : false
                  "
              /></label>
              <label
                >Username<input v-model="cam.username" placeholder="(optional)"
              /></label>
              <label
                >Password
                <input
                  v-model="cam.password"
                  type="text"
                  placeholder="or $CAMERA_PASSWORD env var"
                />
              </label>
            </div>
          </div>
          <p v-if="cfg!.dvr.cameras.length === 0" class="hint">
            No cameras configured.
          </p>
          <p class="hint">
            Camera fields support environment variable references
            (e.g.&nbsp;<code>$CAMERA_HOST</code>,
            <code>$CAMERA_PASSWORD</code>).
          </p>
        </section>

        <!-- Music -->
        <section v-if="activeSection === 'music'">
          <h2>Music</h2>
          <div
            class="sf-row"
            :class="{ modified: isModified('music.audioDevice') }"
          >
            <label class="sf-label">Audio device</label>
            <button
              v-if="isModified('music.audioDevice')"
              type="button"
              class="sf-reset"
              title="Reset to default"
              @click="reset('music.audioDevice')"
            >
              <i class="fi-sr-rotate-left" />
            </button>
            <span v-else class="sf-reset-placeholder" />
            <select
              class="sf-select"
              :value="getPath('music.audioDevice') as string"
              @change="
                setPath(
                  'music.audioDevice',
                  ($event.target as HTMLSelectElement).value
                )
              "
            >
              <option v-for="dev in audioDevices" :key="dev.id" :value="dev.id">
                {{ dev.name }} ({{ dev.id }})
              </option>
              <option
                v-if="audioDevices.length === 0"
                :value="getPath('music.audioDevice') as string"
              >
                {{ getPath('music.audioDevice') as string }}
              </option>
            </select>
          </div>
          <SettingsField
            label="Volume (%)"
            path="music.volume"
            type="range"
            :min="0"
            :max="100"
          />
          <SettingsField
            label="Tracks needed for Album (%)"
            path="music.albumRequiredPercent"
            type="range"
            :min="0"
            :max="100"
          />
          <SettingsField
            label="Count as played after (%)"
            path="music.playedRequiredPercent"
            type="range"
            :min="0"
            :max="100"
          />
          <SettingsField
            label="Transcode format"
            path="music.transcodeFormat"
            placeholder="aac"
          />
          <SettingsField
            label="Max bitrate (kbps, 0 = off)"
            path="music.maxBitrate"
            type="number"
            :min="0"
          />
          <SettingsField
            label="AcoustID API key"
            path="music.acoustidKey"
            placeholder="Register free at acoustid.org"
          />
          <div
            class="sf-row"
            :class="{ modified: isModified('music.acoustidMinScore') }"
          >
            <label class="sf-label">AcoustID min score (%)</label>
            <button
              v-if="isModified('music.acoustidMinScore')"
              type="button"
              class="sf-reset"
              title="Reset to default"
              @click="reset('music.acoustidMinScore')"
            >
              <i class="fi-sr-rotate-left" />
            </button>
            <span v-else class="sf-reset-placeholder" />
            <input
              v-model.number="acoustidScorePct"
              class="sf-range"
              type="range"
              min="0"
              max="100"
              step="5"
            />
            <span class="sf-range-val">{{ acoustidScorePct }}</span>
          </div>
        </section>
      </div>
    </form>
  </div>
</template>

<style scoped lang="scss">
.settings-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  color: #e0e0e0;
  font-size: 0.9rem;
}

.loading {
  color: #888;
  padding: 2rem;
}

.error-banner {
  background: #5a1a1a;
  border-bottom: 1px solid #a33;
  padding: 0.75rem 1rem;
  color: #f88;
  flex-shrink: 0;
}

.settings-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

// ── Left nav ──────────────────────────────────────────────────────────────────
.settings-nav {
  width: 140px;
  flex-shrink: 0;
  background: #161616;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 0.5rem 0;
  border-right: 1px solid #2a2a2a;
}

.nav-item {
  display: block;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  padding: 0.5rem 1rem;
  color: #aaa;
  font-size: 0.85rem;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s;

  &:hover {
    background: #222;
    color: #e0e0e0;
  }

  &--active {
    background: #1e3a5f;
    color: #90caf9;
  }
}

.nav-spacer {
  flex: 1;
}

.saved-msg {
  color: #4ade80;
  font-size: 0.78rem;
  text-align: center;
  padding: 0.4rem 0.75rem;
}

.error-msg {
  color: #f87171;
  font-size: 0.75rem;
  text-align: center;
  padding: 0.4rem 0.75rem;
  word-break: break-word;
}

.save-btn {
  margin: 0.5rem 0.75rem 0.75rem;
  background: #3b82f6;
  border: none;
  border-radius: 6px;
  color: #fff;
  padding: 0.45rem 0;
  font-size: 0.85rem;
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

// ── Right content ─────────────────────────────────────────────────────────────
.settings-content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 1.5rem 1.5rem 2rem;
}

section {
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

  code {
    font-family: monospace;
    background: #2a2a2a;
    border-radius: 3px;
    padding: 0 3px;
    color: #aaa;
  }
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

// ── Inline sf-row helpers (mirrors SettingsField scoped styles) ───────────────
.sf-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;

  &.modified .sf-label {
    font-weight: 700;
    color: #3b82f6;
  }
}

.sf-reset-placeholder {
  width: 1.4rem;
  flex-shrink: 0;
}

.sf-reset {
  width: 1.4rem;
  flex-shrink: 0;
  background: none;
  border: none;
  color: #3b82f6;
  cursor: pointer;
  padding: 0;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    color: #60a5fa;
  }
}

.sf-label {
  width: 200px;
  flex-shrink: 0;
  color: #aaa;
  font-size: 0.85rem;
}

.sf-input {
  flex: 1;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.85rem;
  font-family: monospace;
  min-width: 0;

  &:focus {
    outline: none;
    border-color: #666;
  }
}

.sf-select {
  flex: 1;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.85rem;
  font-family: monospace;
  min-width: 0;

  &:focus {
    outline: none;
    border-color: #666;
  }
}

.sf-range {
  flex: 1;
  cursor: pointer;
  accent-color: #3b82f6;
  min-width: 0;
}

.sf-range-val {
  width: 2.5rem;
  text-align: right;
  flex-shrink: 0;
  font-size: 0.85rem;
  color: #aaa;
  font-variant-numeric: tabular-nums;
}

.sf-unit {
  color: #666;
  font-size: 0.82rem;
  flex-shrink: 0;
}

// Expander bit assignments: 2-column grid within the group
.bit-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 0.5rem;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid #2a2a2a;
}

// ── DVR cameras ───────────────────────────────────────────────────────────────
.cameras-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 1.25rem 0 0.75rem;
}

.cameras-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #e0e0e0;
  margin: 0;
}

.add-camera-btn {
  background: none;
  border: 1px solid #3b82f6;
  border-radius: 4px;
  color: #3b82f6;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 0.2rem 0.6rem;

  &:hover {
    background: #1e3a5f;
  }
}

.camera-card {
  background: #222;
  border: 1px solid #333;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  padding: 0.75rem;
}

.camera-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.camera-num {
  font-size: 0.85rem;
  color: #aaa;
  font-weight: 500;
}

.remove-camera-btn {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0;

  &:hover {
    color: #f87171;
  }
}

.camera-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.4rem 0.75rem;

  label {
    display: flex;
    flex-direction: column;
    font-size: 0.78rem;
    color: #999;
    gap: 0.2rem;
  }

  input {
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    font-size: 0.82rem;
    padding: 0.25rem 0.4rem;

    &:focus {
      outline: none;
      border-color: #666;
    }
  }

  .audio-label {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;

    .audio-check {
      width: 1rem;
      height: 1rem;
      padding: 0;
      border: none;
      background: none;
      accent-color: #888;
    }
  }
}
</style>

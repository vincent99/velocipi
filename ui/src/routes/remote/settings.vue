<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Settings',
  icon: 'sliders-h',
  sort: 99,
  headerScreen: false,
};
</script>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { FullConfig } from '@/types/config';

const cfg = ref<FullConfig | null>(null);
const saving = ref(false);
const saved = ref(false);
const error = ref('');

onMounted(async () => {
  try {
    const r = await fetch('/config?full=true');
    if (!r.ok) throw new Error(await r.text());
    cfg.value = await r.json();
  } catch (e: unknown) {
    error.value = 'Failed to load config: ' + String(e);
  }
});

async function save() {
  if (!cfg.value) return;
  saving.value = true;
  error.value = '';
  saved.value = false;
  try {
    const r = await fetch('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg.value),
    });
    if (!r.ok) throw new Error(await r.text());
    saved.value = true;
    setTimeout(() => { saved.value = false; }, 3000);
  } catch (e: unknown) {
    error.value = 'Save failed: ' + String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="settings-page">
    <div v-if="!cfg && !error" class="loading">Loading…</div>
    <div v-if="error" class="error-banner">{{ error }}</div>

    <form v-if="cfg" @submit.prevent="save">

      <!-- Server -->
      <section>
        <h2>Server</h2>
        <div class="field">
          <label>Listen address</label>
          <input v-model="cfg.addr" type="text" placeholder="0.0.0.0:8080" />
        </div>
        <div class="field">
          <label>App URL</label>
          <input v-model="cfg.appUrl" type="text" placeholder="http://localhost:8081/panel/" />
        </div>
        <div class="field">
          <label>I²C device</label>
          <input v-model="cfg.i2cDevice" type="text" placeholder="/dev/i2c-1" />
        </div>
        <div class="field">
          <label>Ping interval</label>
          <input v-model="cfg.pingInterval" type="text" placeholder="1s" />
        </div>
      </section>

      <!-- Display -->
      <section>
        <h2>Display</h2>
        <div class="field-group">
          <h3>OLED</h3>
          <div class="field">
            <label>SPI port</label>
            <input v-model="cfg.oled.spiPort" type="text" placeholder="/dev/spidev0.0" />
          </div>
          <div class="field">
            <label>SPI speed</label>
            <input v-model="cfg.oled.spiSpeed" type="text" placeholder="2.40MHz" />
          </div>
          <div class="field">
            <label>GPIO chip</label>
            <input v-model="cfg.oled.gpioChip" type="text" placeholder="gpiochip0" />
          </div>
          <div class="field">
            <label>DC pin</label>
            <input v-model.number="cfg.oled.dcPin" type="number" min="0" />
          </div>
          <div class="field">
            <label>Reset pin</label>
            <input v-model.number="cfg.oled.resetPin" type="number" min="0" />
          </div>
          <div class="field field-checkbox">
            <label>Flip display</label>
            <input v-model="cfg.oled.flip" type="checkbox" />
          </div>
        </div>

        <div class="field-group">
          <h3>Screen</h3>
          <div class="field">
            <label>FPS</label>
            <input v-model.number="cfg.screen.fps" type="number" min="1" max="60" />
          </div>
          <div class="field">
            <label>Splash image</label>
            <input v-model="cfg.screen.splashImage" type="text" placeholder="ui/public/img/logo.png" />
          </div>
          <div class="field">
            <label>Splash duration</label>
            <input v-model="cfg.screen.splashDuration" type="text" placeholder="2s" />
          </div>
        </div>
      </section>

      <!-- UI -->
      <section>
        <h2>UI</h2>
        <div class="field">
          <label>Tail number</label>
          <input v-model="cfg.ui.tail" type="text" placeholder="N711ME" />
        </div>
        <div class="field">
          <label>Header color</label>
          <div class="color-field">
            <input v-model="cfg.ui.headerColor" type="color" class="color-swatch" />
            <input v-model="cfg.ui.headerColor" type="text" class="color-text" placeholder="#3b82f6" />
          </div>
        </div>

        <div class="field-group">
          <h3>Panel</h3>
          <div class="field">
            <label>Width (px)</label>
            <input v-model.number="cfg.ui.panel.width" type="number" min="1" />
          </div>
          <div class="field">
            <label>Height (px)</label>
            <input v-model.number="cfg.ui.panel.height" type="number" min="1" />
          </div>
        </div>

        <div class="field-group">
          <h3>Nav menu</h3>
          <div class="field">
            <label>Hide delay (ms)</label>
            <input v-model.number="cfg.ui.navMenu.hideDelay" type="number" min="0" />
          </div>
          <div class="field">
            <label>Cell width (px)</label>
            <input v-model.number="cfg.ui.navMenu.cellWidth" type="number" min="1" />
          </div>
        </div>

        <div class="field-group">
          <h3>Key map</h3>
          <div class="keymap-grid">
            <template v-for="(label, key) in {
              up: 'Up', down: 'Down', left: 'Left', right: 'Right', enter: 'Enter',
              joyLeft: 'Joy left', joyRight: 'Joy right',
              innerLeft: 'Inner left', innerRight: 'Inner right',
              outerLeft: 'Outer left', outerRight: 'Outer right'
            }" :key="key">
              <label>{{ label }}</label>
              <input v-model="(cfg.ui.keyMap as Record<string,string>)[key]" type="text" class="key-input" />
            </template>
          </div>
        </div>
      </section>

      <!-- Hardware -->
      <section>
        <h2>Hardware</h2>

        <div class="field-group">
          <h3>Air sensor (BME280)</h3>
          <div class="field">
            <label>I²C address</label>
            <input v-model.number="cfg.airSensor.address" type="number" min="0" max="127" />
          </div>
          <div class="field">
            <label>Poll interval</label>
            <input v-model="cfg.airSensor.interval" type="text" placeholder="1s" />
          </div>
        </div>

        <div class="field-group">
          <h3>Light sensor (VEML6030)</h3>
          <div class="field">
            <label>I²C address</label>
            <input v-model.number="cfg.lightSensor.address" type="number" min="0" max="127" />
          </div>
          <div class="field">
            <label>Poll interval</label>
            <input v-model="cfg.lightSensor.interval" type="text" placeholder="1s" />
          </div>
        </div>

        <div class="field-group">
          <h3>Expander (SX1509)</h3>
          <div class="field">
            <label>I²C address</label>
            <input v-model.number="cfg.expander.address" type="number" min="0" max="127" />
          </div>
          <div class="field">
            <label>Poll interval</label>
            <input v-model="cfg.expander.interval" type="text" placeholder="2ms" />
          </div>
          <h4>Bit assignments</h4>
          <div class="keymap-grid">
            <template v-for="(label, key) in {
              knobCenter: 'Knob center', knobInner: 'Knob inner (A)',
              knobOuter: 'Knob outer (A)', led: 'LED',
              joyCenter: 'Joy center', joyDown: 'Joy down',
              joyUp: 'Joy up', joyRight: 'Joy right',
              joyLeft: 'Joy left', joyKnob: 'Joy knob (A)'
            }" :key="key">
              <label>{{ label }}</label>
              <input v-model.number="(cfg.expander.bits as Record<string,number>)[key]" type="number" min="0" max="15" class="key-input" />
            </template>
          </div>
        </div>
      </section>

      <!-- Tires -->
      <section>
        <h2>TPMS sensors</h2>
        <p class="hint">One Bluetooth address per line.</p>
        <div class="field-group">
          <h3>Nose</h3>
          <textarea :value="cfg.tires.nose.join('\n')"
            @input="cfg!.tires.nose = ($event.target as HTMLTextAreaElement).value.split('\n').map(s => s.trim()).filter(Boolean)"
            rows="2" placeholder="4a:a0:00:00:eb:02" />
        </div>
        <div class="field-group">
          <h3>Left</h3>
          <textarea :value="cfg.tires.left.join('\n')"
            @input="cfg!.tires.left = ($event.target as HTMLTextAreaElement).value.split('\n').map(s => s.trim()).filter(Boolean)"
            rows="2" placeholder="4a:88:00:00:72:70" />
        </div>
        <div class="field-group">
          <h3>Right</h3>
          <textarea :value="cfg.tires.right.join('\n')"
            @input="cfg!.tires.right = ($event.target as HTMLTextAreaElement).value.split('\n').map(s => s.trim()).filter(Boolean)"
            rows="2" placeholder="4a:85:00:00:d7:38" />
        </div>
      </section>

      <!-- Save bar -->
      <div class="save-bar">
        <span v-if="saved" class="saved-msg">Saved. Restart the server to apply changes.</span>
        <span v-if="error" class="error-msg">{{ error }}</span>
        <button type="submit" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
      </div>

    </form>
  </div>
</template>

<style scoped lang="scss">
.settings-page {
  max-width: 640px;
  margin: 0 auto;
  padding: 1.5rem 1rem 4rem;
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

.field-group {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;

  h3 {
    font-size: 0.8rem;
    font-weight: 600;
    color: #aaa;
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  h4 {
    font-size: 0.75rem;
    color: #888;
    margin: 0.75rem 0 0.5rem;
  }
}

.field {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.6rem;

  &:last-child { margin-bottom: 0; }

  label {
    min-width: 140px;
    color: #aaa;
    flex-shrink: 0;
  }

  input[type="text"],
  input[type="number"] {
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

  &.field-checkbox {
    input[type="checkbox"] {
      width: 1.1rem;
      height: 1.1rem;
      cursor: pointer;
      accent-color: #3b82f6;
    }
  }
}

.color-field {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
}

.color-swatch {
  width: 2rem !important;
  height: 2rem !important;
  padding: 0 !important;
  border-radius: 4px !important;
  cursor: pointer;
  flex: none !important;
}

.color-text {
  flex: 1;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.85rem;
  font-family: monospace;

  &:focus { outline: none; border-color: #666; }
}

.keymap-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.4rem 1rem;
  align-items: center;

  label {
    color: #aaa;
    font-size: 0.85rem;
  }
}

.key-input {
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.25rem 0.4rem;
  font-size: 0.85rem;
  font-family: monospace;
  width: 100%;
  box-sizing: border-box;

  &:focus { outline: none; border-color: #666; }
}

.hint {
  color: #666;
  font-size: 0.8rem;
  margin: 0 0 0.75rem;
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

  &:focus { outline: none; border-color: #666; }
}

.save-bar {
  position: sticky;
  bottom: 0;
  background: #1a1a1a;
  border-top: 1px solid #333;
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0 -1rem -4rem;

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

    &:hover:not(:disabled) { background: #2563eb; }
    &:disabled { opacity: 0.5; cursor: default; }
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

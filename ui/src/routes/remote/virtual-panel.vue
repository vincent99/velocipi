<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'Virtual Panel',
  icon: 'gamepad',
  sort: 98,
};
</script>

<script setup lang="ts">
import { computed } from 'vue';
import ScreenViewer from '@/components/remote/ScreenViewer.vue';
import KeyRelay from '@/components/shared/KeyRelay.vue';
import { useWebSocket } from '@/composables/useWebSocket';
import { useDeviceState } from '@/composables/useDeviceState';
import type { LogicalKey } from '@/types/ws';

const { send } = useWebSocket();
const { ledState } = useDeviceState();

const ledMode = computed(() => ledState.value?.mode ?? 'off');

// Encoder keys: just a tap (keydown + keyup immediately)
function press(key: LogicalKey) {
  send({ type: 'key', eventType: 'keydown', key });
  send({ type: 'key', eventType: 'keyup', key });
}

// Held keys (arrows, enter): keydown on press, keyup on release
function keydown(key: LogicalKey, e: Event) {
  e.preventDefault();
  send({ type: 'key', eventType: 'keydown', key });
}

function keyup(key: LogicalKey) {
  send({ type: 'key', eventType: 'keyup', key });
}

// Unified pointer handlers that work for both mouse and touch
function pointerdown(key: LogicalKey, e: Event) {
  e.preventDefault();
  send({ type: 'key', eventType: 'keydown', key });
}

function pointerup(key: LogicalKey) {
  send({ type: 'key', eventType: 'keyup', key });
}
</script>

<template>
  <KeyRelay />
  <div class="vp-shell">

    <!-- Left cluster: joystick grid with LED in top-right cell -->
    <div class="joy-grid">
      <div />
      <button class="ctrl-btn"
        @pointerdown="pointerdown('up', $event)" @pointerup="pointerup('up')" @pointercancel="pointerup('up')"
      ><i class="fi-sr-angle-up" /></button>
      <div class="led-cell"><div class="led-circle" :class="ledMode" /></div>
      <button class="ctrl-btn"
        @pointerdown="pointerdown('left', $event)" @pointerup="pointerup('left')" @pointercancel="pointerup('left')"
      ><i class="fi-sr-angle-left" /></button>
      <div class="enc-ring">
        <button class="enc-half enc-half-l" @click="press('joy-left')"><span class="mirror">⤸</span></button>
        <button class="enc-half enc-half-r" @click="press('joy-right')">⤸</button>
      </div>
      <button class="ctrl-btn"
        @pointerdown="pointerdown('right', $event)" @pointerup="pointerup('right')" @pointercancel="pointerup('right')"
      ><i class="fi-sr-angle-right" /></button>
      <div />
      <button class="ctrl-btn"
        @pointerdown="pointerdown('down', $event)" @pointerup="pointerup('down')" @pointercancel="pointerup('down')"
      ><i class="fi-sr-angle-down" /></button>
      <div />
    </div>

    <!-- Center: screen -->
    <div class="vp-center">
      <div class="screen-box">
        <ScreenViewer />
      </div>
    </div>

    <!-- Right cluster: two concentric encoder rings, each split left/right -->
    <div class="vp-right">
      <div class="enc-ring enc-ring-outer">
        <button class="enc-half enc-half-l enc-half-outer" @click="press('outer-left')"><span class="mirror">⤸</span></button>
        <button class="enc-half enc-half-r enc-half-outer" @click="press('outer-right')">⤸</button>
        <div class="enc-ring enc-ring-inner">
          <button class="enc-half enc-half-l" @click="press('inner-left')"><span class="mirror">⤸</span></button>
          <button class="enc-half enc-half-r" @click="press('inner-right')">⤸</button>
          <button class="knob-enter"
            @pointerdown.stop="pointerdown('enter', $event)" @pointerup.stop="pointerup('enter')" @pointercancel.stop="pointerup('enter')"
          >●</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped lang="scss">
.vp-shell {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1.25rem 1.5rem;
  background: #2a2a2a;
  border-radius: 12px;
  border: 1px solid #444;
  width: fit-content;
  user-select: none;
  touch-action: none;

  button {
    outline: none;
    -webkit-tap-highlight-color: transparent;
    &:focus-visible { outline: none; }
  }
}

.led-cell {
  display: flex;
  align-items: center;
  justify-content: center;
}

.led-circle {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid #555;
  background: transparent;
  transition: background 0.15s, box-shadow 0.15s;

  &.on {
    background: #e53e3e;
    box-shadow: 0 0 6px #e53e3e;
    border-color: #e53e3e;
  }

  &.blink {
    background: #e53e3e;
    box-shadow: 0 0 6px #e53e3e;
    border-color: #e53e3e;
    animation: led-blink 500ms step-start infinite;
  }
}

@keyframes led-blink {
  50% { background: transparent; box-shadow: none; }
}

.joy-grid {
  display: grid;
  grid-template-columns: repeat(3, 2.4rem);
  grid-template-rows: repeat(3, 2.4rem);
  gap: 3px;
  align-items: center;
  justify-items: center;
}

/* Shared encoder ring: circular container with two absolute half-buttons */
.enc-ring {
  position: relative;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}

/* joy-encoder on left cluster */
.joy-grid .enc-ring {
  width: 2.4rem;
  height: 2.4rem;
  border: 2px solid #555;
  background: #1e1e1e;
}

/* Right cluster rings */
.enc-ring-outer {
  width: 6rem;
  height: 6rem;
  border: 2px solid #555;
  background: #1e1e1e;
}

.enc-ring-inner {
  width: 3.8rem;
  height: 3.8rem;
  border: 2px solid #666;
  background: #2e2e2e;
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  overflow: hidden;
  z-index: 2;
}

.enc-half {
  position: absolute;
  top: 0;
  bottom: 0;
  background: none;
  border: none;
  color: #aaa;
  font-size: 1.4rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 0;
  z-index: 3;
  transition: background 0.1s, color 0.1s;

  &:hover { color: #fff; background: rgba(255,255,255,0.1); }
  &:active { color: #fff; background: rgba(255,255,255,0.2); }
}

.enc-half-l {
  left: 0;
  width: 50%;
  justify-content: flex-start;
  padding-left: 6%;
}

.enc-half-outer {
  z-index: 1;
  font-size: 1.8rem;
}

.enc-half-outer.enc-half-l {
  padding-left: 2%;
}

.enc-half-outer.enc-half-r {
  padding-right: 2%;
}

.mirror {
  display: inline-block;
  transform: scaleX(-1);
}

.enc-half-r {
  right: 0;
  width: 50%;
  justify-content: flex-end;
  padding-right: 6%;
}

/* ── Shared directional button ── */
.ctrl-btn {
  width: 2.2rem;
  height: 2.2rem;
  border-radius: 6px;
  background: #3a3a3a;
  border: 1px solid #555;
  color: #ccc;
  font-size: 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.1s, transform 0.05s;

  &:hover { background: #4a4a4a; }
  &:active { background: #555; transform: scale(0.93); }
}


/* ── Center screen ── */
.vp-center {
  flex-shrink: 0;
}

.screen-box {
  background: #111;
  border: 2px solid #555;
  border-radius: 4px;
  line-height: 0;
  padding: 4px;
}

/* ── Right cluster ── */
.vp-right {
  display: flex;
  align-items: center;
  justify-content: center;
}

.knob-enter {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: #555;
  border: 1px solid #777;
  color: #aaa;
  font-size: 0.5rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  z-index: 4;
  transition: background 0.1s;

  &:hover { background: #666; }
  &:active { background: #777; }
}
</style>

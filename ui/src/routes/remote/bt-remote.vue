<script lang="ts">
import type { PanelMeta } from '@/types/config';
export const remoteMeta: PanelMeta = {
  name: 'BT Remote',
  icon: 'bluetooth',
  sort: 16,
};
</script>

<script setup lang="ts">
import { computed } from 'vue';
import { useBTRemote } from '@/composables/useBTRemote';

const {
  btDevices,
  btPlayer,
  scan,
  stopScan,
  pair,
  connect,
  disconnect,
  forget,
  playPause,
  next,
  previous,
} = useBTRemote();

const track = computed(() => btPlayer.value?.track ?? null);
const isPlaying = computed(() => btPlayer.value?.status === 'playing');
const hasSession = computed(() => btPlayer.value !== null);

const elapsedSec = computed(() => (btPlayer.value?.position ?? 0) / 1000);
const durationSec = computed(() => (track.value?.duration ?? 0) / 1000);
const remainingSec = computed(() => {
  const rem = durationSec.value - elapsedSec.value;
  return rem > 0 ? rem : 0;
});

function formatTime(sec: number): string {
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${m}:${ss.toString().padStart(2, '0')}`;
}

function deviceLabel(d: { name: string; address: string }) {
  return d.name || d.address;
}
</script>

<template>
  <div class="bt-page">
    <!-- Now playing -->
    <div class="bt-section">
      <h2>Now Playing</h2>
      <template v-if="hasSession">
        <div class="np-title">{{ track?.title || '—' }}</div>
        <div class="np-sub">
          <span v-if="track?.artist">{{ track.artist }}</span>
          <span v-if="track?.artist && track?.album" class="np-sep">—</span>
          <span v-if="track?.album">{{ track.album }}</span>
        </div>
        <div class="np-progress">
          <span class="time-label">{{ formatTime(elapsedSec) }}</span>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{
                width: durationSec
                  ? Math.min(100, (elapsedSec / durationSec) * 100) + '%'
                  : '0%',
              }"
            />
          </div>
          <span class="time-label">-{{ formatTime(remainingSec) }}</span>
        </div>

        <div class="transport">
          <button class="ctrl-btn" title="Previous" @click="previous">
            ⏮
          </button>
          <button
            class="ctrl-btn ctrl-btn--main"
            :title="isPlaying ? 'Pause' : 'Play'"
            @click="playPause"
          >
            {{ isPlaying ? '⏸' : '▶' }}
          </button>
          <button class="ctrl-btn" title="Next" @click="next">⏭</button>
        </div>
      </template>
      <div v-else class="np-empty">No active media session</div>
    </div>

    <!-- Devices -->
    <div class="bt-section">
      <div class="devices-header">
        <h2>Devices</h2>
        <div class="scan-btns">
          <button class="bt-btn" @click="scan">Scan</button>
          <button class="bt-btn" @click="stopScan">Stop</button>
        </div>
      </div>

      <div v-if="btDevices.length === 0" class="np-empty">
        No devices found yet — tap Scan
      </div>

      <div v-for="d in btDevices" :key="d.address" class="device-row">
        <div class="device-info">
          <div class="device-name">{{ deviceLabel(d) }}</div>
          <div class="device-badges">
            <span v-if="d.connected" class="badge badge--connected"
              >Connected</span
            >
            <span v-else-if="d.paired" class="badge">Paired</span>
            <span class="device-address">{{ d.address }}</span>
          </div>
        </div>
        <div class="device-actions">
          <button v-if="!d.paired" class="bt-btn" @click="pair(d.address)">
            Pair
          </button>
          <button
            v-else-if="!d.connected"
            class="bt-btn"
            @click="connect(d.address)"
          >
            Connect
          </button>
          <button v-else class="bt-btn" @click="disconnect(d.address)">
            Disconnect
          </button>
          <button
            v-if="d.paired"
            class="bt-btn bt-btn--danger"
            @click="forget(d.address)"
          >
            Forget
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.bt-page {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.bt-section {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  padding: 0.75rem 1rem;

  h2 {
    font-size: 0.75rem;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0 0 0.5rem;
  }
}

.np-empty {
  color: #888;
  font-size: 0.85rem;
  padding: 0.5rem 0;
}

.np-title {
  font-weight: 600;
  font-size: 1.1rem;
}

.np-sub {
  font-size: 0.85rem;
  color: #aaa;
  margin-top: 0.15rem;
}

.np-sep {
  margin: 0 0.35rem;
  color: #666;
}

.np-progress {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.time-label {
  font-size: 0.78rem;
  color: #888;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.progress-bar {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: #333;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #3b82f6;
}

.transport {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 1rem;
}

.ctrl-btn {
  background: none;
  border: 1px solid transparent;
  color: #ccc;
  border-radius: 4px;
  padding: 0.4rem 0.7rem;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: #2a2a2a;
    color: #fff;
  }

  &--main {
    font-size: 1.3rem;
    padding: 0.4rem 0.9rem;
    background: #1e3a5f;
    color: #90caf9;
    border-color: #2a5a9f;

    &:hover {
      background: #2a4a7f;
      color: #fff;
    }
  }
}

.devices-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.scan-btns {
  display: flex;
  gap: 0.5rem;
}

.bt-btn {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0.35rem 0.75rem;
  transition: background 0.15s;

  &:hover {
    background: rgba(255, 255, 255, 0.15);
  }

  &--danger {
    color: #f87171;
    border-color: rgba(248, 113, 113, 0.3);

    &:hover {
      background: rgba(239, 68, 68, 0.15);
    }
  }
}

.device-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  gap: 0.75rem;
}

.device-info {
  min-width: 0;
}

.device-name {
  font-weight: 600;
  font-size: 0.95rem;
}

.device-badges {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.15rem;
}

.badge {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #aaa;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  padding: 0.1rem 0.4rem;

  &--connected {
    color: #4ade80;
    background: rgba(74, 222, 128, 0.15);
  }
}

.device-address {
  font-size: 0.75rem;
  color: #666;
  font-variant-numeric: tabular-nums;
}

.device-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}
</style>

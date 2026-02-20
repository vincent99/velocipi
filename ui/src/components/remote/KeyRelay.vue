<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import type { LogicalKey } from '../../types/ws';
import { useWebSocket } from '../../composables/useWebSocket';

const { send } = useWebSocket();

const jsToLogical: Record<string, LogicalKey> = {
  ArrowLeft: 'left',
  ArrowRight: 'right',
  ArrowUp: 'up',
  ArrowDown: 'down',
  Enter: 'enter',
  '[': 'joy-left',
  ']': 'joy-right',
  ';': 'inner-left',
  "'": 'inner-right',
  ',': 'outer-left',
  '.': 'outer-right',
};

const KNOB_KEYS = new Set(['[', ']', ';', "'", ',', '.']);

function relayKey(eventType: 'keydown' | 'keyup', jsKey: string) {
  const key = jsToLogical[jsKey];
  if (!key) {
    return;
  }
  send({ type: 'key', eventType, key });
}

function onKeyDown(e: KeyboardEvent) {
  if (!(e.key in jsToLogical)) {
    return;
  }
  e.preventDefault();
  if (KNOB_KEYS.has(e.key)) {
    relayKey('keydown', e.key);
    relayKey('keyup', e.key);
  } else if (!e.repeat) {
    relayKey('keydown', e.key);
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (e.key in jsToLogical && !KNOB_KEYS.has(e.key)) {
    e.preventDefault();
    relayKey('keyup', e.key);
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown);
  document.addEventListener('keyup', onKeyUp);
});
onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown);
  document.removeEventListener('keyup', onKeyUp);
});
</script>

<template><!-- renders nothing; handles keyboard relay only --></template>

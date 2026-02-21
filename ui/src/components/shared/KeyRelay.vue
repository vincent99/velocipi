<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue';
import type { LogicalKey } from '@/types/ws';
import { useWebSocket } from '@/composables/useWebSocket';
import { useConfig } from '@/composables/useConfig';

const { send } = useWebSocket();
const { config } = useConfig();

const jsToLogical = computed<Record<string, LogicalKey>>(() => {
  const km = config.value?.keyMap;
  if (!km) {
    return {};
  }
  return {
    [km.up]: 'up',
    [km.down]: 'down',
    [km.left]: 'left',
    [km.right]: 'right',
    [km.enter]: 'enter',
    [km.joyLeft]: 'joy-left',
    [km.joyRight]: 'joy-right',
    [km.innerLeft]: 'inner-left',
    [km.innerRight]: 'inner-right',
    [km.outerLeft]: 'outer-left',
    [km.outerRight]: 'outer-right',
  };
});

const knobKeys = computed<Set<string>>(() => {
  const km = config.value?.keyMap;
  if (!km) {
    return new Set();
  }
  return new Set([
    km.joyLeft,
    km.joyRight,
    km.innerLeft,
    km.innerRight,
    km.outerLeft,
    km.outerRight,
  ]);
});

function relayKey(eventType: 'keydown' | 'keyup', jsKey: string) {
  const key = jsToLogical.value[jsKey];
  if (!key) {
    return;
  }
  send({ type: 'key', eventType, key });
}

function isFormField(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

function onKeyDown(e: KeyboardEvent) {
  if (!(e.key in jsToLogical.value) || isFormField(e.target)) {
    return;
  }

  e.preventDefault();

  if (knobKeys.value.has(e.key)) {
    relayKey('keydown', e.key);
    relayKey('keyup', e.key);
  } else if (!e.repeat) {
    relayKey('keydown', e.key);
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (e.key in jsToLogical.value && !knobKeys.value.has(e.key) && !isFormField(e.target)) {
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

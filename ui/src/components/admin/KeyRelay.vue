<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import type { KeyMsg } from '../../types/ws'

const emit = defineEmits<{ key: [msg: KeyMsg] }>()

const RELAY_KEYS = new Set([
  'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
  'Enter', '[', ']', ';', "'", ',', '.',
])
const KNOB_KEYS = new Set(['[', ']', ';', "'", ',', '.'])

function relayKey(eventType: 'keydown' | 'keyup', key: string) {
  emit('key', { type: 'key', eventType, key })
}

function onKeyDown(e: KeyboardEvent) {
  if (!RELAY_KEYS.has(e.key)) return
  e.preventDefault()
  if (KNOB_KEYS.has(e.key)) {
    relayKey('keydown', e.key)
    relayKey('keyup', e.key)
  } else if (!e.repeat) {
    relayKey('keydown', e.key)
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (RELAY_KEYS.has(e.key) && !KNOB_KEYS.has(e.key)) {
    e.preventDefault()
    relayKey('keyup', e.key)
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown)
  document.addEventListener('keyup', onKeyUp)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('keyup', onKeyUp)
})
</script>

<template><!-- renders nothing; handles keyboard relay only --></template>

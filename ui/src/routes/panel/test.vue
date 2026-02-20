<script lang="ts">
import type { PanelMeta } from '../../../types/config';
export const panelMeta: PanelMeta = { name: 'Test 1', icon: '⚙' };
</script>

<script setup lang="ts">
import KnobCounters from '../../components/panel/KnobCounters.vue';
import KeyDisplay from '../../components/panel/KeyDisplay.vue';
</script>

<template>
  <h2>Test 1</h2>
  <KnobCounters />
  <KeyDisplay />
</template>

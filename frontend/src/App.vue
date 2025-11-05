<script lang="ts" setup>
import Layout from './components/Layout.vue'
import { EventsOff, EventsOn } from '../wailsjs/runtime/runtime'
import { onBeforeMount, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {ReadBrightness} from '../wailsjs/go/main/App.js'
import type {brightness} from '../wailsjs/go/models'

const percent = ref(100)

onBeforeMount(async () => {
  const val = await ReadBrightness()
  percent.value = val.percent
})

EventsOn('brightness', (val: brightness.Result) => {
  percent.value = val.percent
})

onBeforeUnmount(() => {
  EventsOff('brightness')
})

watch(percent, (val: number) => {
  const html = document.getElementsByTagName('HTML')[0]
  if ( val >= 50 ) {
    html.classList.add('light')
    html.classList.remove('dark')
  } else {
    html.classList.add('dark')
    html.classList.remove('light')
  }
}, {immediate: true})
</script>

<template>
  <Layout/>
</template>

<style>
HTML.light {
  background-color: white;
}

HTML.dark {
  background-color: black;
}
</style>

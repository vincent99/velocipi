<script setup lang="ts">
import { computed, onBeforeUnmount, PropType, ref } from 'vue';
import { AirReading } from '../types/air';
import { EventsOff, EventsOn } from '../../wailsjs/runtime/runtime'

const temperature = ref<number>(0)
const pressure = ref<number>(0)
const humidity = ref<number>(0)
const dewpoint = ref<number>(0)
const loaded = ref(false)

EventsOn('air', (a: AirReading) => {
  // console.log('On Air: ', a)
  temperature.value = a.tempF
  pressure.value = Math.round(a.pressureFeet/10)*10
  humidity.value = a.humidity
  dewpoint.value = a.dewpointF
  loaded.value = true
})

onBeforeUnmount(() => {
  EventsOff('tire')
})

</script>

<template>
  <template v-if="loaded">
    <el-col :span="3">
      <el-statistic title="Temperature" :value="temperature" suffix="°F"/>
    </el-col>
    <el-col :span="3">
      <el-statistic title="Dew Point" :value="dewpoint" suffix="°F"/>
    </el-col>
    <el-col :span="3">
      <el-statistic title="Humidity" :value="humidity" suffix="%"/>
    </el-col>
    <el-col :span="3">
      <el-statistic title="Cabin Alt" :value="pressure" suffix="'"/>
    </el-col>
  </template>
  <el-col :span="12" v-else>Loading…</el-col>
</template>

<script lang="ts" setup>
import {onBeforeUnmount, reactive, ref, computed} from 'vue'
// import {Greet} from '../../wailsjs/go/main/App'
import { EventsOff, EventsOn } from '../../wailsjs/runtime/runtime'

const ticker = ref<number>()

function formatter(time: number): string {
  if ( !ticker.value ) {
    return '??:??:??'
  }

  const d = new Date(time)
  let h = d.getHours()
  if ( h == 0 ) {
    h = 12
  } else if ( h > 12 ) {
    h -= 12
  }

  const m = d.getMinutes()
  const s = d.getSeconds()

  const out = (h < 10 ? '0' + h : h) + ':' + (m < 10 ? '0' + m : m) + ':' + (s < 10 ? '0' + s : s)

  return out
}

/*
function greet() {
  Greet(data.name).then(result => {
    data.resultText = result
  })
}
*/

EventsOn('ticker', (str: string) => {
  ticker.value = Date.parse(str)
})

onBeforeUnmount(() => {
  EventsOff('ticker')
})

</script>

<template>
  <el-container>
    <el-header style="padding: 0;">
      <el-row :gutter="0">
        <Tires/>
        <Air/>
        <el-col :span="3">
        <el-statistic title="Time" :value="ticker" :formatter="formatter"/>
        </el-col>
      </el-row>
    </el-header>
    <el-container>
      <el-aside width="80px">Aside</el-aside>
      <el-container>
        <el-main>Main</el-main>
      </el-container>
    </el-container>
  </el-container>
</template>

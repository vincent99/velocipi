<script lang="ts" setup>
import {onBeforeUnmount, ref, computed} from 'vue'
import { EventsOff, EventsOn } from '../../../wailsjs/runtime/runtime'
import Inst from './Inst.vue'
import { Tire } from '../../types/tire'

type TireName = "nose"|"left"|"right"
const PREFIX = 'tire-'
const NOSE: TireName = 'nose'
const LEFT: TireName = 'left'
const RIGHT: TireName = 'right'

function loadTire(name: TireName): Tire {
  try {
    const str = localStorage.getItem(`${PREFIX}${name}`)
    if ( str ) {
      const t: Tire = JSON.parse(str)
      if ( t ) {
        return t
      }
    }
  } finally {
    return {} as Tire
  }
}

const nose = ref<Tire>(loadTire(NOSE))
const left = ref<Tire>(loadTire(LEFT))
const right = ref<Tire>(loadTire(RIGHT))

function updateTire(t: Tire) {
  switch ( t.position ) {
    case 'FL':
    case 'FR':
      nose.value = t
      localStorage.setItem(`${PREFIX}${NOSE}`, JSON.stringify(t))
      break
    case 'RL':
      left.value = t
      localStorage.setItem(`${PREFIX}${LEFT}`, JSON.stringify(t))
      break
    case 'RR':
      right.value = t
      localStorage.setItem(`${PREFIX}${RIGHT}`, JSON.stringify(t))
      break
  }
}

const ticker = ref<string>()
const time = computed(() => {
  if ( !ticker.value ) {
    return '??:??:??'
  }

  const d = new Date(Date.parse(ticker.value))
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
})

EventsOn('tire', (t: Tire) => {
  console.log('On Tire: ', t)
  updateTire(t)
})

onBeforeUnmount(() => {
  EventsOff('tire')
})

</script>

<template>
  <Inst label="Left" :tire="left"/>
  <Inst label="Nose" :tire="nose"/>
  <Inst label="Right" :tire="right"/>
</template>

<script lang="ts" setup>
import {onBeforeUnmount, ref, computed} from 'vue'
import { EventsOff, EventsOn } from '../../../wailsjs/runtime/runtime'
import Inst from './Inst.vue'
import { Tire } from '../../types/tire'

function loadTire(name: string): Tire {
  try {
    const str = localStorage.getItem(name)
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

const nose = ref<Tire>(loadTire('nose'))
const left = ref<Tire>(loadTire('left'))
const right = ref<Tire>(loadTire('right'))

function updateTire(t: Tire) {
  switch ( t.position ) {
    case 'FL':
    case 'FR':
      nose.value = t
      localStorage.setItem('nose', JSON.stringify(t))
      break
    case 'RL':
      left.value = t
      localStorage.setItem('left', JSON.stringify(t))
      break
    case 'RR':
      right.value = t
      localStorage.setItem('right', JSON.stringify(t))
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
  <div class="result">
    <div class="tire"><Inst :tire="left" label="Left"/></div>
    <div class="tire"><Inst :tire="nose" label="Nose"/></div>
    <div class="tire"><Inst :tire="right" label="Right"/></div>
  </div>
</template>

<style scoped>
.result {
  display: flex;
}

.tire {
  flex: 1;
}
</style>

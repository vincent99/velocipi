<script lang="ts" setup>
import {onBeforeUnmount, reactive, ref, computed} from 'vue'
// import {Greet} from '../../wailsjs/go/main/App'
import { EventsOff, EventsOn } from '../../wailsjs/runtime/runtime'
import Tires from './Tires/index.vue'

interface Tire {
	position: "FL"|"FR"|"RL"|"RR"
	serial: string
	updated: string
  tempC: number
  tempF: number
	pressureKpa: number
	pressureBar: number
	pressurePsi: number
  voltage: number
  battery: number
  inflation: "flat"|"low"|"decreasing"|"stable"
  rotation: "unknown"|"still"|"starting"|"rolling"
}

function loadTire(name: string): Tire|null {
  try {
    const str = localStorage.getItem(name)
    if ( !str ) {
      return null
    }

    const t: Tire = JSON.parse(str)
    if ( !t ) {
      return null
    }

    return t
  } catch (e) {
    return null
  }
}

const nose = ref<Tire|null>(loadTire('nose'))
const left = ref<Tire|null>(loadTire('left'))
const right = ref<Tire|null>(loadTire('right'))
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

/*
function greet() {
  Greet(data.name).then(result => {
    data.resultText = result
  })
}
*/

EventsOn('ticker', (str) => {
  ticker.value = str
})

EventsOn('tire', (t: Tire) => {
  console.log('On Tire: ', t)
  updateTire(t)
})

onBeforeUnmount(() => {
  EventsOff('ticker')
  EventsOff('tire')
})

</script>

<template>
  <main>
    <div class="result"><b>Time:</b> {{time }}</div>
    <Tires/>
  </main>
</template>

<style scoped>
.result {
  line-height: 20px;
  margin: 1.5rem auto;
}
</style>

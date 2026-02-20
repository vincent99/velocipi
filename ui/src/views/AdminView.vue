<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useWebSocket } from '../composables/useWebSocket'
import { useScreenSocket } from '../composables/useScreenSocket'
import ScreenViewer from '../components/admin/ScreenViewer.vue'
import AirSensor from '../components/admin/AirSensor.vue'
import TpmsPanel from '../components/admin/TpmsPanel.vue'
import LedStatus from '../components/admin/LedStatus.vue'
import KeyRelay from '../components/admin/KeyRelay.vue'
import type { AirReading, Tire, LEDStateMsg, InboundWsMsg, KeyMsg } from '../types/ws'

const { send, onMessage, onClose } = useWebSocket()
const { frameUrl } = useScreenSocket()

const lastPing = ref<string | null>(null)
const airReading = ref<AirReading | null>(null)
const lux = ref<number | null>(null)
const tires = reactive<Map<string, Tire>>(new Map())
const ledState = ref<LEDStateMsg | null>(null)

onMessage((e: MessageEvent) => {
  let msg: InboundWsMsg
  try { msg = JSON.parse(e.data) } catch { return }

  switch (msg.type) {
    case 'ping':
      lastPing.value = 'Last ping: ' + msg.time
      break
    case 'airReading':
      if (msg.reading) airReading.value = msg.reading
      break
    case 'luxReading':
      if (msg.lux != null) lux.value = msg.lux
      break
    case 'tpms':
      if (msg.tire) tires.set(msg.tire.position, msg.tire)
      break
    case 'ledState':
      ledState.value = msg
      break
  }
})
onClose(() => { lastPing.value = 'Disconnected' })

function onKey(msg: KeyMsg) {
  send(msg)
}
</script>

<template>
  <div class="admin">
    <div class="toolbar">
      <span class="ping">{{ lastPing ?? 'Waiting for ping...' }}</span>
      <button @click="send({ type: 'reload' })">Reload</button>
    </div>
    <AirSensor :reading="airReading" :lux="lux" />
    <LedStatus :state="ledState" />
    <TpmsPanel :tires="tires" />
    <ScreenViewer :frame-url="frameUrl" />
    <KeyRelay @key="onKey" />
  </div>
</template>

<style scoped>
.admin {
  font-family: sans-serif;
  margin: 1rem;
  background: #111;
  color: #eee;
  min-height: 100vh;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.ping {
  font-size: 0.9rem;
  color: #aaa;
}
</style>

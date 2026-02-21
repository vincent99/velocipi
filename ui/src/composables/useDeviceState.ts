import { ref, reactive } from 'vue';
import { useWebSocket } from '@/composables/useWebSocket';
import type { AirReading, LEDStateMsg, Tire, InboundWsMsg } from '@/types/ws';

// Module-level state — single subscription, shared across all consumers.
const lastPing = ref<string | null>(null);
const airReading = ref<AirReading | null>(null);
const lux = ref<number | null>(null);
const ledState = ref<LEDStateMsg | null>(null);
const tires = reactive<Map<string, Tire>>(new Map());

let initialised = false;

function init() {
  if (initialised) return;
  initialised = true;

  const { onMessage, onClose } = useWebSocket();

  onMessage((e: MessageEvent) => {
    let msg: InboundWsMsg;
    try {
      msg = JSON.parse(e.data);
    } catch {
      return;
    }

    switch (msg.type) {
      case 'ping':
        lastPing.value = 'Last ping: ' + msg.time;
        break;
      case 'airReading':
        if (msg.reading) airReading.value = msg.reading;
        break;
      case 'luxReading':
        if (msg.lux != null) lux.value = msg.lux;
        break;
      case 'tpms':
        if (msg.tire) tires.set(msg.tire.position, msg.tire);
        break;
      case 'ledState':
        ledState.value = msg;
        break;
    }
  });

  onClose(() => {
    lastPing.value = 'Disconnected';
  });
}

export function useDeviceState() {
  init();
  return { lastPing, airReading, lux, ledState, tires };
}

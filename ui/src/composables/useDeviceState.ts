import { ref, reactive } from 'vue';
import { useWebSocket } from '@/composables/useWebSocket';
import type {
  AirReading,
  LEDStateMsg,
  Tire,
  InboundWsMsg,
  LogicalKey,
} from '@/types/ws';

// Module-level state — single subscription, shared across all consumers.
const lastPing = ref<string | null>(null);
const airReading = ref<AirReading | null>(null);
const lux = ref<number | null>(null);
const ledState = ref<LEDStateMsg | null>(null);
const tires = reactive<Map<string, Tire>>(new Map());
// cameraRecording: camera name → true if actively recording
const cameraRecording = reactive<Map<string, boolean>>(new Map());

// Key echo: tracks which logical keys are currently "active" for visual feedback.
// Encoder keys (tap-only) auto-clear after 150ms; held keys clear on keyup.
const keyEcho = reactive<Map<LogicalKey, boolean>>(new Map());
const keyEchoTimers = new Map<LogicalKey, ReturnType<typeof setTimeout>>();

const ENCODER_KEYS = new Set<LogicalKey>([
  'joy-left',
  'joy-right',
  'inner-left',
  'inner-right',
  'outer-left',
  'outer-right',
]);

function handleKeyEcho(key: LogicalKey, eventType: 'keydown' | 'keyup') {
  if (ENCODER_KEYS.has(key)) {
    keyEcho.set(key, true);
    clearTimeout(keyEchoTimers.get(key));
    keyEchoTimers.set(
      key,
      setTimeout(() => keyEcho.set(key, false), 150)
    );
  } else {
    keyEcho.set(key, eventType === 'keydown');
  }
}

let initialised = false;

function init() {
  if (initialised) {
    return;
  }
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
        if (msg.reading) {
          airReading.value = msg.reading;
        }
        break;
      case 'luxReading':
        if (msg.lux != null) {
          lux.value = msg.lux;
        }
        break;
      case 'tpms':
        if (msg.tire) {
          tires.set(msg.tire.position, msg.tire);
        }
        break;
      case 'ledState':
        ledState.value = msg;
        break;
      case 'keyEcho':
        handleKeyEcho(msg.key, msg.eventType);
        break;
      case 'cameraStatus':
        cameraRecording.set(msg.name, msg.recording);
        break;
    }
  });

  onClose(() => {
    lastPing.value = 'Disconnected';
  });
}

export function useDeviceState() {
  init();
  return {
    lastPing,
    airReading,
    lux,
    ledState,
    tires,
    keyEcho,
    cameraRecording,
  };
}

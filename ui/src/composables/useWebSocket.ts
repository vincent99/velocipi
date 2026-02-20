import { ref } from 'vue';
import type { OutboundWsMsg } from '../types/ws';

const connected = ref(false);
let ws: WebSocket | null = null;
let messageHandler: ((e: MessageEvent) => void) | null = null;
let closeHandler: (() => void) | null = null;

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => {
    connected.value = true;
  };

  ws.onmessage = (e) => messageHandler?.(e);

  ws.onerror = (e) => console.error('ws error', e);

  ws.onclose = () => {
    connected.value = false;
    closeHandler?.();
    setTimeout(connect, 2000);
  };
  (window as any).ws = ws;
}

function send(msg: OutboundWsMsg) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

(window as any).send = send;

export function useWebSocket() {
  if (!ws) {
    connect();
  }

  return {
    get ws() {
      return ws;
    },
    send,
    connected,
    onMessage(handler: (e: MessageEvent) => void) {
      messageHandler = handler;
    },
    onClose(handler: () => void) {
      closeHandler = handler;
    },
  };
}

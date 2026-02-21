import { ref } from 'vue';
import type { OutboundWsMsg } from '../types/ws';

const connected = ref(false);
const dropped = ref(false);
let ws: WebSocket | null = null;
const messageHandlers = new Set<(e: MessageEvent) => void>();
const closeHandlers = new Set<() => void>();

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => {
    connected.value = true;
  };

  ws.onmessage = (e) => messageHandlers.forEach((h) => h(e));

  ws.onerror = (e) => console.error('ws error', e);

  ws.onclose = () => {
    if (connected.value) dropped.value = true;
    connected.value = false;
    closeHandlers.forEach((h) => h());
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
    dropped,
    onMessage(handler: (e: MessageEvent) => void): () => void {
      messageHandlers.add(handler);
      return () => messageHandlers.delete(handler);
    },
    onClose(handler: () => void): () => void {
      closeHandlers.add(handler);
      return () => closeHandlers.delete(handler);
    },
  };
}

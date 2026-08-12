import { ref } from 'vue';
import type { TransmissionRecord } from '@/types';

// A single shared websocket to /ws/transcripts. The backend pushes each new (or
// corrected) TransmissionRecord; subscribers filter by session themselves.
const handlers = new Set<(r: TransmissionRecord) => void>();
const connected = ref(false);
let ws: WebSocket | null = null;
let unloading = false;

window.addEventListener('beforeunload', () => {
  unloading = true;
});

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws/transcripts`);
  ws.onopen = () => (connected.value = true);
  ws.onmessage = (e) => {
    try {
      const rec = JSON.parse(e.data) as TransmissionRecord;
      handlers.forEach((h) => h(rec));
    } catch {
      /* ignore malformed frames */
    }
  };
  ws.onerror = () => ws?.close();
  ws.onclose = () => {
    connected.value = false;
    if (!unloading) setTimeout(connect, 2000);
  };
}

export function useTranscriptFeed() {
  if (!ws) connect();
  return {
    connected,
    onRecord(h: (r: TransmissionRecord) => void): () => void {
      handlers.add(h);
      return () => handlers.delete(h);
    },
  };
}

import { ref } from 'vue';
import type { SessionManifest } from '@/types';

// Shared session list (most-recent first). refresh() re-fetches from the API.
const sessions = ref<SessionManifest[]>([]);

async function refresh(): Promise<void> {
  try {
    const r = await fetch('/api/sessions');
    if (!r.ok) throw new Error(`sessions: ${r.status}`);
    sessions.value = (await r.json()) as SessionManifest[];
  } catch (err) {
    console.error('useSessions: failed to load', err);
  }
}

export function useSessions() {
  return { sessions, refresh };
}

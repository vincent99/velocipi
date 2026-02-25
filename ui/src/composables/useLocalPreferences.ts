import { ref, watch } from 'vue';
import type { Ref } from 'vue';

// Module-level cache so all callers sharing the same key get the same reactive ref.
const cache = new Map<string, Ref<unknown>>();

export function useLocalPref<T>(key: string, defaultValue: T): Ref<T> {
  if (cache.has(key)) {
    return cache.get(key) as Ref<T>;
  }

  let stored: T = defaultValue;
  try {
    const raw = localStorage.getItem(key);
    if (raw !== null) {
      stored = JSON.parse(raw) as T;
    }
  } catch {
    // ignore parse errors — fall back to default
  }

  const r = ref<T>(stored);
  cache.set(key, r as Ref<unknown>);

  watch(r, (v) => {
    try {
      localStorage.setItem(key, JSON.stringify(v));
    } catch {
      // ignore write errors (e.g. private browsing quota)
    }
  });

  return r;
}

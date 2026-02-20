import { ref } from 'vue';
import type { Config } from '../types/config';

const config = ref<Config | null>(null);
let fetchPromise: Promise<void> | null = null;

function load(): Promise<void> {
  if (fetchPromise) {
    return fetchPromise;
  }
  fetchPromise = fetch('/config')
    .then((r) => r.json())
    .then((data) => {
      config.value = data as Config;
    })
    .catch((err) => {
      console.error('useConfig: failed to load /config', err);
    });
  return fetchPromise;
}

export function useConfig() {
  load();
  return { config };
}

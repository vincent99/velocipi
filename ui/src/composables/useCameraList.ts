import { ref } from 'vue';

const cameras = ref<string[]>([]);
let loaded = false;

export function useCameraList() {
  if (!loaded) {
    loaded = true;
    fetch('/cameras')
      .then((r) => (r.ok ? r.json() : []))
      .then((data: { name: string }[]) => {
        cameras.value = data.map((c) => c.name);
      })
      .catch(() => {});
  }
  return { cameras };
}

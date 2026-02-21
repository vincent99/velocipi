import { ref } from 'vue';

export interface CameraInfo {
  name: string;
  audio: boolean;
}

const cameraList = ref<CameraInfo[]>([]);
const cameras = ref<string[]>([]);
let loaded = false;

export function useCameraList() {
  if (!loaded) {
    loaded = true;
    fetch('/cameras')
      .then((r) => (r.ok ? r.json() : []))
      .then((data: { name: string; audio?: boolean }[]) => {
        cameraList.value = data.map((c) => ({
          name: c.name,
          audio: c.audio ?? false,
        }));
        cameras.value = data.map((c) => c.name);
      })
      .catch(() => {});
  }
  return { cameras, cameraList };
}

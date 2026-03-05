import { reactive, computed } from 'vue';

// Module-level singleton — shared across all consumers (panel + local views).
const viewport = reactive({ zoom: 1.0, panX: 0, panY: 0 });

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

function setZoom(z: number) {
  viewport.zoom = clamp(z, 1, 8);
  // Re-clamp pan when zoom changes.
  const maxPan = ((1 - 1 / viewport.zoom) / 2) * 100;
  viewport.panX = clamp(viewport.panX, -maxPan, maxPan);
  viewport.panY = clamp(viewport.panY, -maxPan, maxPan);
}

function adjustZoom(delta: number) {
  setZoom(viewport.zoom + delta);
}

function adjustPan(dx: number, dy: number) {
  const maxPan = ((1 - 1 / viewport.zoom) / 2) * 100;
  viewport.panX = clamp(viewport.panX + dx, -maxPan, maxPan);
  viewport.panY = clamp(viewport.panY + dy, -maxPan, maxPan);
}

function reset() {
  viewport.zoom = 1;
  viewport.panX = 0;
  viewport.panY = 0;
}

export function useVideoViewport() {
  const transformStyle = computed(() => ({
    transform: `scale(${viewport.zoom}) translate(${viewport.panX}%, ${viewport.panY}%)`,
    transformOrigin: 'center center',
    width: '100%',
    height: '100%',
  }));

  return { viewport, transformStyle, setZoom, adjustZoom, adjustPan, reset };
}

import { computed, onMounted, onUnmounted } from 'vue';
import { useConfig } from '@/composables/useConfig';

export interface MusicPanelKeyHandlers {
  playPause?: () => void;
  toNowPlaying?: () => void; // long up
  openNav?: () => void; // short down (layout-level)
  prev?: () => void; // short left
  seekBack?: () => void; // long left
  next?: () => void; // short right
  seekForward?: () => void; // long right
}

/**
 * Handles joystick directional long/short press for the music panel layout.
 * PanelList intercepts joyLeft/joyRight/up/down via capture-phase listeners,
 * so this composable only receives events that PanelList did not consume
 * (i.e. when no PanelList is mounted, e.g. on now-playing).
 */
export function useMusicPanelKeys(handlers: MusicPanelKeyHandlers) {
  const { config } = useConfig();
  const longPressMs = computed(() => config.value?.navMenu.longPressMs ?? 1000);

  // Per-key hold tracking: null = up, number = timer id, -1 = long press fired
  let leftTimer: ReturnType<typeof setTimeout> | null | -1 = null;
  let rightTimer: ReturnType<typeof setTimeout> | null | -1 = null;
  let downTimer: ReturnType<typeof setTimeout> | null | -1 = null;
  let upTimer: ReturnType<typeof setTimeout> | null | -1 = null;

  function clearTimer(timer: ReturnType<typeof setTimeout> | null | -1): null {
    if (timer !== null && timer !== -1) {
      clearTimeout(timer);
    }
    return null;
  }

  function onKeyDown(e: KeyboardEvent) {
    const km = config.value?.keyMap;
    if (!km) {
      return;
    }

    if (e.key === km.left && leftTimer === null) {
      e.preventDefault();
      leftTimer = setTimeout(() => {
        leftTimer = -1;
        handlers.seekBack?.();
      }, longPressMs.value);
      return;
    }

    if (e.key === km.right && rightTimer === null) {
      e.preventDefault();
      rightTimer = setTimeout(() => {
        rightTimer = -1;
        handlers.seekForward?.();
      }, longPressMs.value);
      return;
    }

    if (e.key === km.down && downTimer === null) {
      e.preventDefault();
      downTimer = setTimeout(() => {
        downTimer = -1;
        // Long down at layout level has no assigned action currently
      }, longPressMs.value);
      return;
    }

    if (e.key === km.up && upTimer === null) {
      e.preventDefault();
      upTimer = setTimeout(() => {
        upTimer = -1;
        handlers.toNowPlaying?.();
      }, longPressMs.value);
      return;
    }
  }

  function onKeyUp(e: KeyboardEvent) {
    const km = config.value?.keyMap;
    if (!km) {
      return;
    }

    if (e.key === km.left) {
      e.preventDefault();
      if (leftTimer === -1) {
        leftTimer = null;
      } else if (leftTimer !== null) {
        leftTimer = clearTimer(leftTimer);
        handlers.prev?.();
      }
      return;
    }

    if (e.key === km.right) {
      e.preventDefault();
      if (rightTimer === -1) {
        rightTimer = null;
      } else if (rightTimer !== null) {
        rightTimer = clearTimer(rightTimer);
        handlers.next?.();
      }
      return;
    }

    if (e.key === km.down) {
      e.preventDefault();
      if (downTimer === -1) {
        downTimer = null;
      } else if (downTimer !== null) {
        downTimer = clearTimer(downTimer);
        handlers.openNav?.();
      }
      return;
    }

    if (e.key === km.up) {
      e.preventDefault();
      if (upTimer === -1) {
        upTimer = null;
      } else if (upTimer !== null) {
        upTimer = clearTimer(upTimer);
        handlers.playPause?.();
      }
      return;
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('keyup', onKeyUp);
  });

  onUnmounted(() => {
    document.removeEventListener('keydown', onKeyDown);
    document.removeEventListener('keyup', onKeyUp);
    leftTimer = clearTimer(leftTimer);
    rightTimer = clearTimer(rightTimer);
    downTimer = clearTimer(downTimer);
    upTimer = clearTimer(upTimer);
  });
}

import { ref, computed, onMounted, onUnmounted } from 'vue';
import type { Ref } from 'vue';
import { useConfig } from '@/composables/useConfig';

// Provided to child PanelControl components via inject.
export interface PanelGridContext {
  registerControl: (col: number, row: number) => number; // returns the control's stable slot index
  selectedIndex: Ref<number>;
  activeIndex: Ref<number | null>;
  registerCallbacks: (
    index: number,
    onInner: (dir: 'left' | 'right') => void,
    onConfirm: () => void,
    onCancel: () => void
  ) => void;
}

export const PANEL_GRID_KEY = Symbol('panelGrid');

/**
 * usePanelGrid — manages focus/active state and key routing for a panel grid.
 *
 * Inner-knob behaviour (always active):
 *  - innerLeft/innerRight cycle the selected control (when no control is active).
 *  - enter activates the selected control.
 *  - When a control is active:
 *    - innerLeft/innerRight are routed to onInner callback.
 *    - enter short press = confirm; long press (≥ longPressMs) = cancel.
 *  - Outer-knob keys are NOT consumed here (NavMenu owns them).
 *
 * Joystick behaviour (when usesJoystick is false, i.e. grid owns the joystick):
 *  - up/down/left/right move selection spatially between controls.
 *  - joyLeft/joyRight route to onInner on the active control (or no-op if not active).
 *  - Long press down (≥ longPressMs): activates selected control, or confirms active one.
 *  - Long press up (≥ longPressMs): cancels active control.
 */
export function usePanelGrid(options?: {
  usesJoystick?: boolean;
  onInner?: (index: number, dir: 'left' | 'right') => void;
  onConfirm?: (index: number) => void;
  onCancel?: (index: number) => void;
}) {
  const { config } = useConfig();
  const longPressMs = computed(() => config.value?.navMenu.longPressMs ?? 1000);
  const usesJoystick = options?.usesJoystick ?? false;

  // Each slot holds the stable index assigned at registration time plus its grid position.
  const slots = ref<{ index: number; col: number; row: number }[]>([]);
  const controlCount = ref(0);
  const selectedIndex = ref(0);
  const activeIndex = ref<number | null>(null);

  // Navigation order: slot indices sorted by col then row (top-to-bottom, left-to-right).
  const navOrder = computed(() =>
    [...slots.value]
      .sort((a, b) => a.col - b.col || a.row - b.row)
      .map((s) => s.index)
  );

  let enterDownAt: number | null = null;
  let joyDownAt: number | null = null;

  function deactivate(confirm: boolean) {
    const idx = activeIndex.value;
    activeIndex.value = null;
    if (idx === null) {
      return;
    }
    if (confirm) {
      options?.onConfirm?.(idx);
    } else {
      options?.onCancel?.(idx);
    }
  }

  // Find the slot for a given control index.
  function slotOf(index: number) {
    return slots.value.find((s) => s.index === index);
  }

  // Among all slots, find the best candidate in a spatial direction from the current selection.
  // Strategy: must be strictly on the correct side, prefer the closest on the primary axis,
  // break ties with the secondary axis distance.
  function moveSelection(dir: 'up' | 'down' | 'left' | 'right') {
    const cur = slotOf(selectedIndex.value);
    if (!cur) {
      return;
    }
    let best: (typeof slots.value)[0] | null = null;
    let bestPrimary = Infinity;
    let bestSecondary = Infinity;

    for (const s of slots.value) {
      if (s.index === cur.index) {
        continue;
      }
      let primary: number;
      let secondary: number;
      let valid: boolean;
      if (dir === 'up') {
        valid = s.row < cur.row;
        primary = cur.row - s.row;
        secondary = Math.abs(s.col - cur.col);
      } else if (dir === 'down') {
        valid = s.row > cur.row;
        primary = s.row - cur.row;
        secondary = Math.abs(s.col - cur.col);
      } else if (dir === 'left') {
        valid = s.col < cur.col;
        primary = cur.col - s.col;
        secondary = Math.abs(s.row - cur.row);
      } else {
        valid = s.col > cur.col;
        primary = s.col - cur.col;
        secondary = Math.abs(s.row - cur.row);
      }
      if (!valid) {
        continue;
      }
      if (
        primary < bestPrimary ||
        (primary === bestPrimary && secondary < bestSecondary)
      ) {
        best = s;
        bestPrimary = primary;
        bestSecondary = secondary;
      }
    }
    if (best) {
      selectedIndex.value = best.index;
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    const km = config.value?.keyMap;
    if (!km || controlCount.value === 0) {
      return;
    }

    // Inner-knob enter.
    if (e.key === km.enter) {
      e.preventDefault();
      enterDownAt = Date.now();
      return;
    }

    if (activeIndex.value !== null) {
      // Active: route inner-knob to the control.
      if (e.key === km.innerLeft) {
        e.preventDefault();
        options?.onInner?.(activeIndex.value, 'left');
      } else if (e.key === km.innerRight) {
        e.preventDefault();
        options?.onInner?.(activeIndex.value, 'right');
      }
    } else {
      // Not active: inner-knob moves selection (clamped, not wrapping).
      const order = navOrder.value;
      const pos = order.indexOf(selectedIndex.value);
      if (e.key === km.innerLeft) {
        e.preventDefault();
        if (pos > 0) {
          selectedIndex.value = order[pos - 1]!;
        }
      } else if (e.key === km.innerRight) {
        e.preventDefault();
        if (pos < order.length - 1) {
          selectedIndex.value = order[pos + 1]!;
        }
      }
    }

    // Joystick controls (only when the grid owns the joystick).
    if (!usesJoystick) {
      if (e.key === km.up) {
        e.preventDefault();
        if (activeIndex.value === null) {
          moveSelection('up');
        }
        // While active, up is handled on keyup (cancel).
      } else if (e.key === km.down) {
        e.preventDefault();
        if (activeIndex.value === null) {
          joyDownAt = Date.now();
        }
        // While active, down is handled on keyup (confirm).
      } else if (e.key === km.left || e.key === km.joyLeft) {
        e.preventDefault();
        if (activeIndex.value !== null) {
          options?.onInner?.(activeIndex.value, 'left');
        } else if (e.key === km.left) {
          moveSelection('left');
        }
      } else if (e.key === km.right || e.key === km.joyRight) {
        e.preventDefault();
        if (activeIndex.value !== null) {
          options?.onInner?.(activeIndex.value, 'right');
        } else if (e.key === km.right) {
          moveSelection('right');
        }
      }
    }
  }

  function onKeyUp(e: KeyboardEvent) {
    const km = config.value?.keyMap;
    if (!km) {
      return;
    }

    // Inner-knob enter.
    if (e.key === km.enter) {
      e.preventDefault();
      if (enterDownAt === null) {
        return;
      }
      const held = Date.now() - enterDownAt;
      enterDownAt = null;
      if (activeIndex.value !== null) {
        deactivate(held < longPressMs.value);
      } else {
        activeIndex.value = selectedIndex.value;
      }
      return;
    }

    // Joystick controls (only when the grid owns the joystick).
    if (!usesJoystick) {
      if (e.key === km.down) {
        e.preventDefault();
        if (activeIndex.value !== null) {
          deactivate(true); // any press down while active = confirm
        } else {
          if (joyDownAt === null) {
            return;
          }
          const held = Date.now() - joyDownAt;
          joyDownAt = null;
          if (held >= longPressMs.value) {
            activeIndex.value = selectedIndex.value; // long press down = activate
          } else {
            moveSelection('down'); // short press down = move selection down
          }
        }
      } else if (e.key === km.up && activeIndex.value !== null) {
        e.preventDefault();
        deactivate(false); // any press up while active = cancel
      }
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('keyup', onKeyUp);
  });

  onUnmounted(() => {
    document.removeEventListener('keydown', onKeyDown);
    document.removeEventListener('keyup', onKeyUp);
  });

  function registerControl(col: number, row: number): number {
    const idx = controlCount.value;
    controlCount.value++;
    slots.value.push({ index: idx, col, row });
    return idx;
  }

  return {
    selectedIndex,
    activeIndex,
    controlCount,
    registerControl,
  };
}

import { ref, computed, onMounted, onUnmounted } from 'vue';
import type { Ref } from 'vue';
import { useConfig } from '@/composables/useConfig';

// Provided to child PanelControl components via inject.
export interface PanelGridContext {
  registerControl: (
    col: number,
    row: number,
    colSpan: number,
    rowSpan: number
  ) => number; // returns the control's stable slot index
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

  // Each slot holds the stable index assigned at registration time plus its grid position and span.
  const slots = ref<
    {
      index: number;
      col: number;
      row: number;
      colSpan: number;
      rowSpan: number;
    }[]
  >([]);
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
  // Joystick hold timers. null = key not held; timer id = key held, not yet fired; -1 = timer already fired.
  let joyDownTimer: ReturnType<typeof setTimeout> | null | -1 = null;
  let joyUpTimer: ReturnType<typeof setTimeout> | null | -1 = null;

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

  // Returns true if two ranges [a, a+spanA) and [b, b+spanB) overlap.
  function rangesOverlap(a: number, spanA: number, b: number, spanB: number) {
    return a < b + spanB && a + spanA > b;
  }

  // Among all slots, find the best candidate in a spatial direction from the current selection.
  // Sort key: (overlaps secondary axis ? 0 : 1, primary distance, secondary distance).
  // This ensures controls that share column/row range are preferred over distant ones.
  function moveSelection(dir: 'up' | 'down' | 'left' | 'right') {
    const cur = slotOf(selectedIndex.value);
    if (!cur) {
      return;
    }
    let best: (typeof slots.value)[0] | null = null;
    let bestOverlap = 1;
    let bestPrimary = Infinity;
    let bestSecondary = Infinity;

    for (const s of slots.value) {
      if (s.index === cur.index) {
        continue;
      }
      let primary: number;
      let secondary: number;
      let valid: boolean;
      let overlap: number;
      if (dir === 'up') {
        valid = s.row < cur.row;
        primary = cur.row - (s.row + s.rowSpan - 1);
        secondary = Math.abs(s.col - cur.col);
        overlap = rangesOverlap(cur.col, cur.colSpan, s.col, s.colSpan) ? 0 : 1;
      } else if (dir === 'down') {
        valid = s.row + s.rowSpan - 1 > cur.row + cur.rowSpan - 1;
        primary = s.row - (cur.row + cur.rowSpan - 1);
        secondary = Math.abs(s.col - cur.col);
        overlap = rangesOverlap(cur.col, cur.colSpan, s.col, s.colSpan) ? 0 : 1;
      } else if (dir === 'left') {
        valid = s.col < cur.col;
        primary = cur.col - (s.col + s.colSpan - 1);
        secondary = Math.abs(s.row - cur.row);
        overlap = rangesOverlap(cur.row, cur.rowSpan, s.row, s.rowSpan) ? 0 : 1;
      } else {
        valid = s.col + s.colSpan - 1 > cur.col + cur.colSpan - 1;
        primary = s.col - (cur.col + cur.colSpan - 1);
        secondary = Math.abs(s.row - cur.row);
        overlap = rangesOverlap(cur.row, cur.rowSpan, s.row, s.rowSpan) ? 0 : 1;
      }
      if (!valid) {
        continue;
      }
      if (
        overlap < bestOverlap ||
        (overlap === bestOverlap && primary < bestPrimary) ||
        (overlap === bestOverlap &&
          primary === bestPrimary &&
          secondary < bestSecondary)
      ) {
        best = s;
        bestOverlap = overlap;
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
        } else if (joyUpTimer === null) {
          // Hold up while active: cancel after longPressMs.
          joyUpTimer = setTimeout(() => {
            joyUpTimer = -1;
            deactivate(false);
          }, longPressMs.value);
        }
      } else if (e.key === km.down) {
        e.preventDefault();
        if (activeIndex.value !== null) {
          // Hold down while active: confirm after longPressMs.
          if (joyDownTimer === null) {
            joyDownTimer = setTimeout(() => {
              joyDownTimer = -1;
              deactivate(true);
            }, longPressMs.value);
          }
        } else if (joyDownTimer === null) {
          // Hold down while inactive: activate after longPressMs.
          joyDownTimer = setTimeout(() => {
            joyDownTimer = -1;
            activeIndex.value = selectedIndex.value;
          }, longPressMs.value);
        }
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
        if (joyDownTimer === -1) {
          // Timer already fired — action already taken, just reset.
          joyDownTimer = null;
        } else if (joyDownTimer !== null) {
          // Released before longPressMs fired.
          clearTimeout(joyDownTimer);
          joyDownTimer = null;
          if (activeIndex.value !== null) {
            deactivate(true); // short press down while active = confirm
          } else {
            moveSelection('down'); // short press down while inactive = move
          }
        }
      } else if (e.key === km.up) {
        e.preventDefault();
        if (joyUpTimer === -1) {
          // Timer already fired — action already taken, just reset.
          joyUpTimer = null;
        } else if (joyUpTimer !== null) {
          // Released before longPressMs fired — short press up while active = cancel immediately.
          clearTimeout(joyUpTimer);
          joyUpTimer = null;
          if (activeIndex.value !== null) {
            deactivate(false);
          }
        }
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
    if (joyDownTimer !== null && joyDownTimer !== -1) {
      clearTimeout(joyDownTimer);
    }
    if (joyUpTimer !== null && joyUpTimer !== -1) {
      clearTimeout(joyUpTimer);
    }
  });

  function registerControl(
    col: number,
    row: number,
    colSpan = 1,
    rowSpan = 1
  ): number {
    const idx = controlCount.value;
    controlCount.value++;
    slots.value.push({ index: idx, col, row, colSpan, rowSpan });
    return idx;
  }

  return {
    selectedIndex,
    activeIndex,
    controlCount,
    registerControl,
  };
}

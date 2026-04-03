<script setup lang="ts">
import { ref, computed } from 'vue';
import {
  useQueueActions,
  type QueueAction,
} from '@/composables/useQueueActions';

interface Props {
  ids: number[];
  variant?: 'menu' | 'bar' | 'detail';
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'bar',
});

const { queueActionPref, isVisible, executeAction } = useQueueActions();

const dropdownOpen = ref(false);

const allActions: QueueAction[] = [
  'playNow',
  'queueNext',
  'queueLater',
  'append',
];

const actionLabels: Record<QueueAction, string> = {
  playNow: 'Play Now',
  queueNext: 'Queue Next',
  queueLater: 'Queue Later',
  append: 'Append',
};

const visibleActions = computed<QueueAction[]>(() =>
  allActions.filter((a) => isVisible(a))
);

const primaryAction = computed<QueueAction>(() => {
  if (isVisible(queueActionPref.value)) {
    return queueActionPref.value;
  }
  return visibleActions.value[0] ?? 'playNow';
});

const dropdownActions = computed<QueueAction[]>(() =>
  visibleActions.value.filter((a) => a !== primaryAction.value)
);

function handleMain() {
  dropdownOpen.value = false;
  executeAction(primaryAction.value, props.ids);
}

function handleDropdownItem(action: QueueAction) {
  dropdownOpen.value = false;
  executeAction(action, props.ids);
}

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value;
}
</script>

<template>
  <div class="queue-action-btn" :class="`variant-${variant}`">
    <div class="qa-row" :class="{ 'qa-row--solo': dropdownActions.length === 0 }">
      <button class="qa-main" @click="handleMain">
        {{ actionLabels[primaryAction] }}
      </button>
      <button
        v-if="dropdownActions.length > 0"
        class="qa-chevron"
        @click.stop="toggleDropdown"
      >
        ▾
      </button>
    </div>
    <div v-if="dropdownOpen && dropdownActions.length > 0" class="qa-dropdown" @click.stop>
      <button
        v-for="action in dropdownActions"
        :key="action"
        @click="handleDropdownItem(action)"
      >
        {{ actionLabels[action] }}
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.queue-action-btn {
  position: relative;
  display: inline-flex;
  align-items: stretch;

  .qa-row {
    display: inline-flex;
    align-items: stretch;
  }
}

// ── Shared button reset ──────────────────────────────────────────────────────

button {
  cursor: pointer;
  font-size: inherit;
  line-height: 1;
}

// ── menu variant ─────────────────────────────────────────────────────────────

.variant-menu {
  display: block;
  width: 100%;

  // Main row: label takes remaining space, chevron at far right
  .qa-row {
    display: flex;
    align-items: stretch;
    width: 100%;
  }

  .qa-main {
    flex: 1;
    background: none;
    border: none;
    color: #e0e0e0;
    padding: 0.4rem 0.75rem;
    text-align: left;
    font-size: 0.85rem;
    cursor: pointer;

    &:hover {
      background: #3b82f6;
      color: #fff;
    }
  }

  .qa-chevron {
    background: none;
    border: none;
    color: #777;
    padding: 0.4rem 0.5rem;
    font-size: 0.7rem;
    cursor: pointer;
    flex-shrink: 0;

    &:hover {
      background: #3b82f6;
      color: #fff;
    }
  }

  // Inline expansion: sub-items indented inside the same menu
  .qa-dropdown {
    button {
      display: block;
      width: 100%;
      background: none;
      border: none;
      color: #c0c0c0;
      padding: 0.35rem 0.75rem 0.35rem 1.5rem;
      text-align: left;
      font-size: 0.82rem;
      cursor: pointer;

      &:hover {
        background: #3b82f6;
        color: #fff;
      }
    }
  }
}

// ── bar variant ───────────────────────────────────────────────────────────────

.variant-bar {
  .qa-row--solo .qa-main {
    border-right: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
  }

  .qa-main {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-right: none;
    border-radius: 4px 0 0 4px;
    color: #90caf9;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;

    &:hover {
      background: rgba(255, 255, 255, 0.2);
      color: #fff;
    }
  }

  .qa-chevron {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0 4px 4px 0;
    color: #90caf9;
    padding: 0.25rem 0.3rem;
    font-size: 0.75rem;

    &:hover {
      background: rgba(255, 255, 255, 0.2);
      color: #fff;
    }
  }

  .qa-dropdown {
    position: absolute;
    bottom: 100%;
    left: 0;
    margin-bottom: 4px;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 0.25rem 0;
    z-index: 310;
    min-width: 120px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
    white-space: nowrap;

    button {
      display: block;
      width: 100%;
      background: none;
      border: none;
      color: #e0e0e0;
      padding: 0.4rem 0.75rem;
      text-align: left;
      font-size: 0.85rem;
      cursor: pointer;

      &:hover {
        background: #3b82f6;
        color: #fff;
      }
    }
  }
}

// ── detail variant ────────────────────────────────────────────────────────────

.variant-detail {
  .qa-row--solo .qa-main {
    border-right: 1px solid #2a5a9f;
    border-radius: 4px;
  }

  .qa-main {
    background: #1e3a5f;
    border: 1px solid #2a5a9f;
    border-right: none;
    border-radius: 4px 0 0 4px;
    color: #90caf9;
    padding: 0.25rem 0.6rem;
    font-size: 0.78rem;

    &:hover {
      background: #2a4a7f;
    }
  }

  .qa-chevron {
    background: #1e3a5f;
    border: 1px solid #2a5a9f;
    border-radius: 0 4px 4px 0;
    color: #90caf9;
    padding: 0.25rem 0.4rem;
    font-size: 0.75rem;

    &:hover {
      background: #2a4a7f;
    }
  }

  .qa-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 4px;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 0.25rem 0;
    z-index: 310;
    min-width: 120px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
    white-space: nowrap;

    button {
      display: block;
      width: 100%;
      background: none;
      border: none;
      color: #e0e0e0;
      padding: 0.4rem 0.75rem;
      text-align: left;
      font-size: 0.85rem;
      cursor: pointer;

      &:hover {
        background: #3b82f6;
        color: #fff;
      }
    }
  }
}
</style>

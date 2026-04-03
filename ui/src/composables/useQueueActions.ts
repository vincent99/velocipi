import { ref, computed } from 'vue';
import { useDeviceState } from '@/composables/useDeviceState';
import { useLocalPref } from '@/composables/useLocalPreferences';

export type QueueAction = 'playNow' | 'queueNext' | 'queueLater' | 'append';

// Module-level singleton state
const enqueueIndex = ref(-1);
const queueActionPref = useLocalPref<QueueAction>(
  'music.queueAction',
  'queueNext'
);

export function useQueueActions() {
  const { musicState } = useDeviceState();

  const canQueueNext = computed(() => (musicState.value?.queueLength ?? 0) > 0);
  const canQueueLater = computed(
    () => enqueueIndex.value >= 0 && (musicState.value?.queueLength ?? 0) > 0
  );
  const canAppend = computed(() => (musicState.value?.queueLength ?? 0) > 0);

  function isVisible(action: QueueAction): boolean {
    if (action === 'queueNext') {
      return canQueueNext.value;
    }
    if (action === 'queueLater') {
      return canQueueLater.value;
    }
    if (action === 'append') {
      return canAppend.value;
    }
    // playNow is always visible
    return true;
  }

  async function playNow(ids: number[]): Promise<void> {
    await fetch('/music/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ songIds: ids }),
    });
    enqueueIndex.value = -1;
  }

  async function queueNext(ids: number[]): Promise<void> {
    const preFetchQueueIndex = musicState.value?.queueIndex ?? 0;
    await fetch('/music/queue/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ songIds: ids }),
    });
    enqueueIndex.value = preFetchQueueIndex + 1 + ids.length;
  }

  async function queueLater(ids: number[]): Promise<void> {
    const index = enqueueIndex.value;
    await fetch('/music/queue/insert-at', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ songIds: ids, index }),
    });
    enqueueIndex.value += ids.length;
  }

  async function appendToQueue(ids: number[]): Promise<void> {
    await fetch('/music/queue/append', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ songIds: ids }),
    });
  }

  async function executeAction(
    action: QueueAction,
    ids: number[]
  ): Promise<void> {
    const prefWasVisible = isVisible(queueActionPref.value);

    if (action === 'playNow') {
      await playNow(ids);
    } else if (action === 'queueNext') {
      await queueNext(ids);
    } else if (action === 'queueLater') {
      await queueLater(ids);
    } else {
      await appendToQueue(ids);
    }

    if (prefWasVisible) {
      queueActionPref.value = action;
    }
  }

  return {
    enqueueIndex,
    queueActionPref,
    canQueueNext,
    canQueueLater,
    canAppend,
    isVisible,
    playNow,
    queueNext,
    queueLater,
    appendToQueue,
    executeAction,
  };
}

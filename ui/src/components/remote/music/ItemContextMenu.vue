<script setup lang="ts">
import { computed } from 'vue';
import {
  useQueueActions,
  type QueueAction,
} from '@/composables/useQueueActions';
import ContextMenu from '@/components/remote/music/ContextMenu.vue';

interface Props {
  x: number;
  y: number;
  ids: number[] | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  close: [];
}>();

const { isVisible, executeAction } = useQueueActions();

const allActions: QueueAction[] = [
  'playNow',
  'queueNext',
  'queueLater',
  'append',
];

const visibleActions = computed<QueueAction[]>(() =>
  allActions.filter((a) => isVisible(a))
);

const actionLabels: Record<QueueAction, string> = {
  playNow: 'Play Now',
  queueNext: 'Queue Next',
  queueLater: 'Queue Later',
  append: 'Append',
};

async function handleAction(action: QueueAction) {
  if (!props.ids) {
    return;
  }
  await executeAction(action, props.ids);
  emit('close');
}
</script>

<template>
  <ContextMenu :x="x" :y="y" @close="emit('close')">
    <div v-if="ids === null" class="ctx-loading">Loading…</div>
    <template v-else>
      <button
        v-for="action in visibleActions"
        :key="action"
        @click="handleAction(action)"
      >
        {{ actionLabels[action] }}
      </button>
    </template>
  </ContextMenu>
</template>

<style scoped lang="scss">
.ctx-loading {
  color: #888;
  padding: 0.4rem 0.75rem;
  font-size: 0.85rem;
}

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
</style>

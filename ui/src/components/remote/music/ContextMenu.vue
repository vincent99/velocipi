<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue';

interface Props {
  x: number;
  y: number;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  close: [];
}>();

const style = computed(() => {
  const left = Math.min(props.x, window.innerWidth - 180);
  let top: number;
  if (props.y + 300 > window.innerHeight) {
    top = Math.max(0, props.y - 300);
  } else {
    top = props.y;
  }
  return { left: `${left}px`, top: `${top}px` };
});

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close');
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown);
});
</script>

<template>
  <Teleport to="body">
    <div
      class="ctx-overlay"
      @click="emit('close')"
      @contextmenu.prevent="emit('close')"
    />
    <div class="ctx-menu" :style="style" @click.stop @contextmenu.stop.prevent>
      <slot />
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.ctx-overlay {
  position: fixed;
  inset: 0;
  z-index: 500;
}

.ctx-menu {
  position: fixed;
  z-index: 501;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.25rem 0;
  min-width: 160px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
  white-space: nowrap;
}
</style>

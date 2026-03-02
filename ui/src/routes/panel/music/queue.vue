<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useDeviceState } from '@/composables/useDeviceState';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import PanelList from '@/components/panel/PanelList.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';

const router = useRouter();
const { musicQueue, musicState } = useDeviceState();
const player = useMusicPlayer();

const selectedIdx = ref(0);

const items = computed<ListItem[]>(() => {
  const entries = musicQueue.value?.entries ?? [];
  const currentIdx = musicState.value?.queueIndex ?? -1;
  return entries.map((e, i) => ({
    label: e.song?.title ?? `Song ${e.songId}`,
    secondary: i === currentIdx ? '▶' : String(i + 1),
    icon: '',
  }));
});

function onSelect(i: number) {
  player.jumpToIndex(i);
  router.push('/panel/music/now-playing');
}

function onHeaderAction() {
  // No bulk action for queue
}
</script>

<template>
  <PanelList
    v-model="selectedIdx"
    :items="items"
    header-label="Queue"
    @select="onSelect"
    @header-action="onHeaderAction"
    @back="router.push('/panel/music/now-playing')"
    @to-now-playing="router.push('/panel/music/now-playing')"
  />
</template>

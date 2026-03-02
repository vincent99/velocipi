<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PanelList from '@/components/panel/PanelList.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';
import type { Decade } from '@/types/music';

const router = useRouter();
const decades = ref<Decade[]>([]);
const selectedIdx = ref(0);

onMounted(async () => {
  try {
    const r = await fetch('/music/decades');
    if (r.ok) {
      decades.value = (await r.json()) as Decade[];
    }
  } catch {
    /* ignore */
  }
});

const items = computed<ListItem[]>(() =>
  decades.value.map((d) => ({
    label: d.decade ? `${d.decade}s` : 'Unknown',
    secondary: String(d.trackCount),
    icon: '',
  }))
);

function onSelect(i: number) {
  const d = decades.value[i];
  if (!d) {
    return;
  }
  router.push({
    path: '/panel/music/songs',
    query: { decade: String(d.decade) },
  });
}
</script>

<template>
  <PanelList
    v-model="selectedIdx"
    :items="items"
    header-label="Decades"
    @select="onSelect"
    @back="router.back()"
    @to-now-playing="router.push('/panel/music/now-playing')"
  />
</template>

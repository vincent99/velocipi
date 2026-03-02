<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PanelList from '@/components/panel/PanelList.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';
import type { Genre } from '@/types/music';

const router = useRouter();
const genres = ref<Genre[]>([]);
const selectedIdx = ref(0);

onMounted(async () => {
  try {
    const r = await fetch('/music/genres');
    if (r.ok) {
      genres.value = (await r.json()) as Genre[];
    }
  } catch {
    /* ignore */
  }
});

const items = computed<ListItem[]>(() =>
  genres.value.map((g) => ({
    label: g.genre,
    secondary: String(g.trackCount),
    icon: '',
  }))
);

function onSelect(i: number) {
  const g = genres.value[i];
  if (!g) {
    return;
  }
  router.push({ path: '/panel/music/songs', query: { genre: g.genre } });
}
</script>

<template>
  <PanelList
    v-model="selectedIdx"
    :items="items"
    header-label="Genres"
    @select="onSelect"
    @back="router.back()"
    @to-now-playing="router.push('/panel/music/now-playing')"
  />
</template>

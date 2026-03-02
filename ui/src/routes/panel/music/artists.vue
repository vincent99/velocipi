<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import PanelList from '@/components/panel/PanelList.vue';
import ActionMenu from '@/components/panel/ActionMenu.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';
import type { ActionItem } from '@/components/panel/ActionMenu.vue';
import type { Artist } from '@/types/music';

const router = useRouter();
const player = useMusicPlayer();

const artists = ref<Artist[]>([]);
const selectedIdx = ref(0);
const actionMenuRef = ref<InstanceType<typeof ActionMenu> | null>(null);
const actionTargetArtist = ref<string | null>(null);

async function loadArtists() {
  try {
    const r = await fetch('/music/artists');
    if (!r.ok) {
      return;
    }
    artists.value = (await r.json()) as Artist[];
  } catch {
    // ignore
  }
}

onMounted(loadArtists);

const items = computed<ListItem[]>(() =>
  artists.value.map((a) => ({
    label: a.artist,
    secondary: `${a.albumCount}`,
    icon: '',
  }))
);

function onSelect(i: number) {
  const a = artists.value[i];
  if (!a) {
    return;
  }
  router.push({ path: '/panel/music/albums', query: { artist: a.artist } });
}

function onAction(i: number) {
  actionTargetArtist.value = artists.value[i]?.artist ?? null;
  actionMenuRef.value?.show();
}

function onHeaderAction() {
  actionTargetArtist.value = null;
  actionMenuRef.value?.show();
}

const actionItems: ActionItem[] = [
  { key: 'enqueue', label: 'Enqueue' },
  { key: 'append', label: 'Append' },
  { key: 'replace', label: 'Replace' },
];

async function onActionSelect(key: string) {
  const artist = actionTargetArtist.value;
  const params = artist ? `?artist=${encodeURIComponent(artist)}` : '';
  try {
    const r = await fetch(`/music/songs${params}`);
    if (!r.ok) {
      return;
    }
    const data = await r.json();
    const ids: number[] = (data.songs ?? data).map((s: { id: number }) => s.id);
    if (key === 'enqueue') {
      player.enqueue(ids);
    } else if (key === 'append') {
      player.appendQueue(ids);
    } else if (key === 'replace') {
      player.replaceQueue(ids);
    }
  } catch {
    // ignore
  }
}
</script>

<template>
  <div class="page">
    <PanelList
      v-model="selectedIdx"
      :items="items"
      header-label="Artists"
      @select="onSelect"
      @action="onAction"
      @header-action="onHeaderAction"
      @back="router.back()"
      @to-now-playing="router.push('/panel/music/now-playing')"
    />
    <ActionMenu
      ref="actionMenuRef"
      :items="actionItems"
      @select="onActionSelect"
    />
  </div>
</template>

<style scoped>
.page {
  position: relative;
  width: 100%;
  height: var(--panel-h, 64px);
}
</style>

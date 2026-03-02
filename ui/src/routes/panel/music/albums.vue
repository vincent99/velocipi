<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import PanelList from '@/components/panel/PanelList.vue';
import ActionMenu from '@/components/panel/ActionMenu.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';
import type { ActionItem } from '@/components/panel/ActionMenu.vue';
import type { Album } from '@/types/music';

const route = useRoute();
const router = useRouter();
const player = useMusicPlayer();

const albums = ref<Album[]>([]);
const selectedIdx = ref(0);
const actionMenuRef = ref<InstanceType<typeof ActionMenu> | null>(null);
const actionTargetAlbum = ref<Album | null>(null);

const artist = computed(() => (route.query.artist as string) ?? '');
const headerLabel = computed(() =>
  artist.value ? `Albums · ${artist.value}` : 'Albums'
);

async function loadAlbums() {
  selectedIdx.value = 0;
  const params = artist.value
    ? `?artist=${encodeURIComponent(artist.value)}`
    : '';
  try {
    const r = await fetch(`/music/albums${params}`);
    if (!r.ok) {
      return;
    }
    albums.value = (await r.json()) as Album[];
  } catch {
    // ignore
  }
}

onMounted(loadAlbums);
watch(artist, loadAlbums);

const items = computed<ListItem[]>(() =>
  albums.value.map((a) => ({
    label: a.album,
    secondary: a.year ? String(a.year) : '',
    icon: '',
  }))
);

function onSelect(i: number) {
  const a = albums.value[i];
  if (!a) {
    return;
  }
  const query: Record<string, string> = { artist: a.artist, album: a.album };
  if (a.coverId != null) {
    query.coverId = String(a.coverId);
  }
  router.push({ path: '/panel/music/songs', query });
}

function onAction(i: number) {
  actionTargetAlbum.value = albums.value[i] ?? null;
  actionMenuRef.value?.show();
}

function onHeaderAction() {
  actionTargetAlbum.value = null;
  actionMenuRef.value?.show();
}

const actionItems: ActionItem[] = [
  { key: 'enqueue', label: 'Enqueue' },
  { key: 'append', label: 'Append' },
  { key: 'replace', label: 'Replace' },
];

async function onActionSelect(key: string) {
  const target = actionTargetAlbum.value;
  const params = new URLSearchParams();
  if (target) {
    params.set('artist', target.artist);
    params.set('album', target.album);
  } else if (artist.value) {
    params.set('artist', artist.value);
  }
  try {
    const r = await fetch(`/music/songs?${params}`);
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
      :header-label="headerLabel"
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

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import PanelList from '@/components/panel/PanelList.vue';
import ActionMenu from '@/components/panel/ActionMenu.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';
import type { ActionItem } from '@/components/panel/ActionMenu.vue';
import type { Song } from '@/types/music';

const route = useRoute();
const router = useRouter();
const player = useMusicPlayer();

const songs = ref<Song[]>([]);
const selectedIdx = ref(0);
const actionMenuRef = ref<InstanceType<typeof ActionMenu> | null>(null);
const actionTargetIds = ref<number[]>([]);

const artist = computed(() => (route.query.artist as string) ?? '');
const album = computed(() => (route.query.album as string) ?? '');
const genre = computed(() => (route.query.genre as string) ?? '');
const decade = computed(() => (route.query.decade as string) ?? '');
const playlist = computed(() => (route.query.playlist as string) ?? '');
const smartsearch = computed(() => (route.query.smartsearch as string) ?? '');
const coverId = computed(() => route.query.coverId as string | undefined);

const albumArt = computed(() =>
  coverId.value ? `/music/cover/${coverId.value}` : undefined
);

const headerLabel = computed(() => {
  if (album.value) {
    return `Songs · ${album.value}`;
  }
  if (artist.value) {
    return `Songs · ${artist.value}`;
  }
  if (genre.value) {
    return `Songs · ${genre.value}`;
  }
  if (decade.value) {
    return `Songs · ${decade.value}s`;
  }
  if (playlist.value) {
    return 'Playlist Songs';
  }
  if (smartsearch.value) {
    return 'Search Results';
  }
  return 'Songs';
});

async function loadSongs() {
  selectedIdx.value = 0;
  try {
    let url: string;
    if (playlist.value) {
      url = `/music/playlists/${playlist.value}/songs`;
    } else if (smartsearch.value) {
      url = `/music/smartsearches/${smartsearch.value}/songs`;
    } else {
      const params = new URLSearchParams();
      if (artist.value) {
        params.set('artist', artist.value);
      }
      if (album.value) {
        params.set('album', album.value);
      }
      if (genre.value) {
        params.set('genre', genre.value);
      }
      if (decade.value) {
        params.set('decade', decade.value);
      }
      url = `/music/songs?${params}`;
    }
    const r = await fetch(url);
    if (!r.ok) {
      return;
    }
    const data = await r.json();
    songs.value = (data.songs ?? data) as Song[];
  } catch {
    // ignore fetch errors
  }
}

onMounted(loadSongs);
watch([artist, album, genre, decade, playlist, smartsearch], loadSongs);

const items = computed<ListItem[]>(() =>
  songs.value.map((s) => ({
    label: s.title,
    secondary: s.length ? formatDur(s.length) : '',
    icon: '',
  }))
);

function formatDur(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function onSelect(i: number) {
  const song = songs.value[i];
  if (!song) {
    return;
  }
  player.replaceQueue([song.id]);
  router.push('/panel/music/now-playing');
}

function openActionMenu(ids: number[]) {
  actionTargetIds.value = ids;
  actionMenuRef.value?.show();
}

function onAction(i: number) {
  const song = songs.value[i];
  if (song) {
    openActionMenu([song.id]);
  }
}

function onHeaderAction() {
  openActionMenu(songs.value.map((s) => s.id));
}

const actionItems: ActionItem[] = [
  { key: 'enqueue', label: 'Enqueue' },
  { key: 'append', label: 'Append' },
  { key: 'replace', label: 'Replace' },
];

function onActionSelect(key: string) {
  const ids = actionTargetIds.value;
  if (key === 'enqueue') {
    player.enqueue(ids);
  } else if (key === 'append') {
    player.appendQueue(ids);
  } else if (key === 'replace') {
    player.replaceQueue(ids);
  }
}
</script>

<template>
  <div class="page">
    <PanelList
      v-model="selectedIdx"
      :items="items"
      :header-label="headerLabel"
      :image="albumArt"
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

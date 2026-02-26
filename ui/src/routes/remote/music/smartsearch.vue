<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import SongTable from '@/components/remote/SongTable.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import { useAdmin } from '@/composables/useAdmin';
import type { Song, SmartSearch } from '@/types/music';

const route = useRoute();
const router = useRouter();
const { enqueue, appendQueue, replaceQueue, markSong, favoriteSong } =
  useMusicPlayer();
const { openEdit } = useSongEdit();
const { isAdmin } = useAdmin();

const smartSearch = ref<SmartSearch | null>(null);
const songs = ref<Song[]>([]);
const loading = ref(false);

async function load(id: number) {
  loading.value = true;
  smartSearch.value = null;
  songs.value = [];
  try {
    const [plRes, songsRes] = await Promise.all([
      fetch(`/music/smartsearches`),
      fetch(`/music/smartsearches/${id}/songs`),
    ]);
    if (plRes.ok) {
      const list: SmartSearch[] = await plRes.json();
      smartSearch.value = list.find((p) => p.id === id) ?? null;
    }
    if (songsRes.ok) {
      const data = await songsRes.json();
      songs.value = data.songs ?? [];
    }
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.query.id as string | undefined,
  (id) => {
    if (id) {
      load(Number(id));
    } else {
      smartSearch.value = null;
      songs.value = [];
    }
  },
  { immediate: true }
);

async function handleMark(ids: number[], marked: boolean) {
  await Promise.all(ids.map((id) => markSong(id, marked)));
}

async function handleFavorite(ids: number[], favorite: boolean) {
  await Promise.all(ids.map((id) => favoriteSong(id, favorite)));
}

function handleEdit(ids: number[]) {
  openEdit(
    songs.value.filter((s) => ids.includes(s.id)),
    () => {
      const id = route.query.id as string | undefined;
      if (id) {
        load(Number(id));
      }
    }
  );
}

async function handleDelete() {
  if (!smartSearch.value) {
    return;
  }
  if (!confirm(`Delete smart search "${smartSearch.value.name}"?`)) {
    return;
  }
  await fetch(`/music/smartsearches/${smartSearch.value.id}`, {
    method: 'DELETE',
  });
  router.push('/remote/music/songs');
}
</script>

<template>
  <div class="smartsearch-view">
    <div v-if="smartSearch" class="pl-header">
      <div class="pl-name">{{ smartSearch.name }}</div>
      <div class="pl-actions">
        <button class="pl-btn" @click="replaceQueue(songs.map((s) => s.id))">
          Play Now
        </button>
        <button class="pl-btn" @click="enqueue(songs.map((s) => s.id))">
          Queue Next
        </button>
        <button class="pl-btn" @click="appendQueue(songs.map((s) => s.id))">
          Queue Later
        </button>
        <button
          v-if="isAdmin"
          class="pl-btn pl-btn--danger"
          @click="handleDelete"
        >
          Delete
        </button>
      </div>
    </div>
    <SongTable
      :songs="songs"
      :loading="loading"
      @enqueue="(ids) => enqueue(ids)"
      @append="(ids) => appendQueue(ids)"
      @replace="(ids) => replaceQueue(ids)"
      @mark="handleMark"
      @favorite="handleFavorite"
      @edit="handleEdit"
    />
  </div>
</template>

<style scoped lang="scss">
.smartsearch-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.pl-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.pl-name {
  font-weight: 600;
  font-size: 0.9rem;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pl-actions {
  display: flex;
  gap: 0.4rem;
  flex-shrink: 0;
}

.pl-btn {
  background: #1e3a5f;
  border: 1px solid #2a5a9f;
  color: #90caf9;
  border-radius: 4px;
  padding: 0.25rem 0.6rem;
  font-size: 0.78rem;
  cursor: pointer;

  &:hover {
    background: #2a4a7f;
    color: #fff;
  }

  &--danger {
    background: #3f1a1a;
    border-color: #7f2a2a;
    color: #f48fb1;

    &:hover {
      background: #5a2020;
      color: #fff;
    }
  }
}
</style>

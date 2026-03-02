<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import SongTable from '@/components/remote/SongTable.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Album, Song } from '@/types/music';

const route = useRoute();
const router = useRouter();
const { enqueue, appendQueue, replaceQueue, markSong, favoriteSong } =
  useMusicPlayer();
const { openEdit } = useSongEdit();

const albums = ref<Album[]>([]);
const loading = ref(false);
const albumSongs = ref<Song[]>([]);
const albumSongsLoading = ref(false);

// Derive selected album purely from URL query params
const selectedAlbum = computed(() => {
  const qArtist = route.query.artist as string | undefined;
  const qAlbum = route.query.album as string | undefined;
  if (!qArtist || !qAlbum) {
    return null;
  }
  return (
    albums.value.find((a) => a.artist === qArtist && a.album === qAlbum) ?? null
  );
});

async function load() {
  loading.value = true;
  try {
    const r = await fetch('/music/albums');
    if (r.ok) {
      albums.value = await r.json();
    }
  } finally {
    loading.value = false;
  }
}

load();

async function loadAlbumSongs(album: Album) {
  albumSongsLoading.value = true;
  try {
    const params = new URLSearchParams({
      artist: album.artist,
      album: album.album,
    });
    const r = await fetch(`/music/songs?${params}`);
    if (r.ok) {
      const data = await r.json();
      albumSongs.value = data.songs ?? [];
    }
  } finally {
    albumSongsLoading.value = false;
  }
}

function handleEdit(ids: number[]) {
  const album = selectedAlbum.value;
  openEdit(
    albumSongs.value.filter((s) => ids.includes(s.id)),
    () => {
      if (album) {
        loadAlbumSongs(album);
      }
    }
  );
}

// Load album songs whenever the selection changes
watch(
  selectedAlbum,
  async (album) => {
    if (!album) {
      albumSongs.value = [];
      return;
    }
    await loadAlbumSongs(album);
  },
  { immediate: true }
);

function selectAlbum(album: Album) {
  router.push({ query: { artist: album.artist, album: album.album } });
}

function backToGrid() {
  router.push({ query: {} });
}

const albumSongIds = computed(() => albumSongs.value.map((s) => s.id));

async function handleMark(ids: number[], marked: boolean) {
  await Promise.all(ids.map((id) => markSong(id, marked)));
}

async function handleFavorite(ids: number[], favorite: boolean) {
  await Promise.all(ids.map((id) => favoriteSong(id, favorite)));
}

async function handleDelete(ids: number[]) {
  await fetch('/music/songs/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  albumSongs.value = albumSongs.value.filter((s) => !ids.includes(s.id));
}
</script>

<template>
  <div class="albums-view" :class="{ 'is-grid': !selectedAlbum }">
    <!-- Album detail -->
    <template v-if="selectedAlbum">
      <div class="detail-header">
        <button class="back-btn" @click="backToGrid">← Albums</button>
        <img
          v-if="selectedAlbum.coverId"
          :src="`/music/cover/${selectedAlbum.coverId}`"
          class="detail-cover"
          alt=""
        />
        <img v-else src="/img/no-cover.svg" class="detail-cover" alt="" />
        <div class="detail-info">
          <div class="detail-album">
            {{ selectedAlbum.album || '(Unknown Album)' }}
          </div>
          <div class="detail-artist">{{ selectedAlbum.artist }}</div>
          <div class="detail-year">{{ selectedAlbum.year || '' }}</div>
        </div>
        <div class="detail-actions">
          <button @click="replaceQueue(albumSongIds)">Play Now</button>
          <button @click="enqueue(albumSongIds)">Queue Next</button>
          <button @click="appendQueue(albumSongIds)">Queue Later</button>
        </div>
      </div>
      <SongTable
        :songs="albumSongs"
        :loading="albumSongsLoading"
        :show-album="false"
        :show-artist="false"
        :show-year="false"
        :album-context="true"
        @enqueue="(ids) => enqueue(ids)"
        @append="(ids) => appendQueue(ids)"
        @replace="(ids) => replaceQueue(ids)"
        @mark="handleMark"
        @favorite="handleFavorite"
        @delete="handleDelete"
        @edit="handleEdit"
      />
    </template>

    <!-- Album grid -->
    <template v-else>
      <div v-if="loading" class="grid-loading">Loading…</div>
      <div v-else class="album-grid">
        <div
          v-for="album in albums"
          :key="`${album.artist}|||${album.album}`"
          class="album-card"
          @click="selectAlbum(album)"
        >
          <div class="card-cover-wrap">
            <img
              v-if="album.coverId"
              :src="`/music/cover/${album.coverId}`"
              class="card-cover"
              loading="lazy"
              alt=""
            />
            <img v-else src="/img/no-cover.svg" class="card-cover" alt="" />
          </div>
          <div class="card-info">
            <div class="card-album">{{ album.album || '(Unknown Album)' }}</div>
            <div class="card-artist">{{ album.artist }}</div>
            <div class="card-year">{{ album.year || '' }}</div>
          </div>
        </div>
        <div v-if="albums.length === 0" class="grid-empty">
          No albums found.
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.albums-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  &.is-grid {
    overflow-y: auto;
  }
}

.grid-loading,
.grid-empty {
  color: #555;
  text-align: center;
  padding: 2rem;
}

.album-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 0.75rem;
  padding: 0.75rem;
  align-content: start;
}

.album-card {
  cursor: pointer;
  border-radius: 6px;
  overflow: hidden;
  background: #1a1a1a;
  transition: background 0.15s;

  &:hover {
    background: #242424;
  }
}

.card-cover-wrap {
  aspect-ratio: 1;
  overflow: hidden;
  background: #111;
}

.card-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.card-info {
  padding: 0.4rem 0.5rem;
}

.card-album {
  font-size: 0.78rem;
  font-weight: 600;
  color: #e0e0e0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-artist {
  font-size: 0.72rem;
  color: #aaa;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-year {
  font-size: 0.7rem;
  color: #666;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.75rem;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.back-btn {
  background: none;
  border: 1px solid #444;
  color: #aaa;
  border-radius: 4px;
  padding: 0.3rem 0.6rem;
  font-size: 0.8rem;
  cursor: pointer;
  flex-shrink: 0;
  align-self: center;

  &:hover {
    background: #222;
    color: #e0e0e0;
  }
}

.detail-cover {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}

.detail-info {
  flex: 1;
  min-width: 0;
}

.detail-album {
  font-weight: 700;
  font-size: 1rem;
  color: #e0e0e0;
}

.detail-artist {
  color: #aaa;
  font-size: 0.85rem;
  margin-top: 2px;
}

.detail-year {
  color: #666;
  font-size: 0.78rem;
  margin-top: 2px;
}

.detail-actions {
  display: flex;
  gap: 0.4rem;
  flex-shrink: 0;
  align-self: center;

  button {
    background: #1e3a5f;
    border: 1px solid #2a5a9f;
    color: #90caf9;
    border-radius: 4px;
    padding: 0.25rem 0.6rem;
    font-size: 0.78rem;
    cursor: pointer;

    &:hover {
      background: #2a4a7f;
    }
  }
}
</style>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import SongTable from '@/components/remote/music/SongTable.vue';
import QueueActionButton from '@/components/remote/music/QueueActionButton.vue';
import ItemContextMenu from '@/components/remote/music/ItemContextMenu.vue';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import { useSongEdit } from '@/composables/useSongEdit';
import type { Artist, Song } from '@/types/music';

const route = useRoute();
const router = useRouter();
const { markSong, favoriteSong } = useMusicPlayer();
const { openEdit } = useSongEdit();

function handleEdit(ids: number[]) {
  const artist = selectedArtist.value;
  openEdit(
    artistSongs.value.filter((s) => ids.includes(s.id)),
    () => {
      if (artist) {
        loadArtistSongs(artist);
      }
    }
  );
}

const artists = ref<Artist[]>([]);
const loading = ref(false);
const artistSongs = ref<Song[]>([]);
const artistSongsLoading = ref(false);

// Artist list sort
type ArtistSortCol = 'artist' | 'albums' | 'tracks';
const artistSortCol = ref<ArtistSortCol>('artist');
const artistSortDir = ref<1 | -1>(1);

function cycleArtistSort(col: ArtistSortCol) {
  if (artistSortCol.value === col) {
    artistSortDir.value = artistSortDir.value === 1 ? -1 : 1;
  } else {
    artistSortCol.value = col;
    artistSortDir.value = 1;
  }
}

function artistSortIndicator(col: ArtistSortCol): string {
  if (artistSortCol.value !== col) {
    return '';
  }
  return artistSortDir.value === 1 ? ' ↑' : ' ↓';
}

const sortedArtists = computed<Artist[]>(() => {
  const d = artistSortDir.value;
  return [...artists.value].sort((a, b) => {
    let av: string | number;
    let bv: string | number;
    if (artistSortCol.value === 'artist') {
      av = (a.artistSort || a.artist).toLowerCase();
      bv = (b.artistSort || b.artist).toLowerCase();
    } else if (artistSortCol.value === 'albums') {
      av = a.albumCount;
      bv = b.albumCount;
    } else {
      av = a.trackCount;
      bv = b.trackCount;
    }
    if (av < bv) {
      return -d;
    }
    if (av > bv) {
      return d;
    }
    return 0;
  });
});

// Derive selected artist purely from URL query param
const selectedArtist = computed(() => {
  const qArtist = route.query.artist as string | undefined;
  if (!qArtist) {
    return null;
  }
  return artists.value.find((a) => a.artist === qArtist) ?? null;
});

async function load() {
  loading.value = true;
  try {
    const r = await fetch('/music/artists');
    if (r.ok) {
      artists.value = await r.json();
    }
  } finally {
    loading.value = false;
  }
}

load();

async function loadArtistSongs(artist: Artist) {
  artistSongsLoading.value = true;
  try {
    const params = new URLSearchParams({ artist: artist.artist });
    const r = await fetch(`/music/songs?${params}`);
    if (r.ok) {
      const data = await r.json();
      artistSongs.value = data.songs ?? [];
    }
  } finally {
    artistSongsLoading.value = false;
  }
}

// Load artist songs whenever the selection changes
watch(
  selectedArtist,
  async (artist) => {
    if (!artist) {
      artistSongs.value = [];
      return;
    }
    await loadArtistSongs(artist);
  },
  { immediate: true }
);

function selectArtist(artist: Artist) {
  router.push({ query: { artist: artist.artist } });
}

function backToList() {
  router.push({ query: {} });
}

const artistSongIds = computed(() => artistSongs.value.map((s) => s.id));

const ctxMenu = ref<{ ids: number[] | null; x: number; y: number } | null>(
  null
);

async function onArtistContextMenu(artist: Artist, e: MouseEvent) {
  if (e.metaKey || e.ctrlKey) {
    return;
  }
  e.preventDefault();
  ctxMenu.value = { ids: null, x: e.clientX, y: e.clientY };
  const r = await fetch(
    `/music/songs?artist=${encodeURIComponent(artist.artist)}`
  );
  if (r.ok && ctxMenu.value) {
    const data = await r.json();
    const songs: Song[] = data.songs ?? data;
    ctxMenu.value.ids = songs.map((s) => s.id);
  }
}

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
  artistSongs.value = artistSongs.value.filter((s) => !ids.includes(s.id));
}
</script>

<template>
  <div class="artists-view">
    <!-- Artist detail -->
    <template v-if="selectedArtist">
      <div
        class="detail-header"
        @contextmenu="
          (e) => {
            if (!e.metaKey && !e.ctrlKey) {
              e.preventDefault();
              ctxMenu = { ids: artistSongIds, x: e.clientX, y: e.clientY };
            }
          }
        "
      >
        <button class="back-btn" @click="backToList">← Artists</button>
        <div class="detail-info">
          <div class="detail-name">{{ selectedArtist.artist }}</div>
          <div class="detail-meta">
            {{ selectedArtist.albumCount }}
            album{{ selectedArtist.albumCount === 1 ? '' : 's' }} ·
            {{ selectedArtist.trackCount }} track{{
              selectedArtist.trackCount === 1 ? '' : 's'
            }}
          </div>
        </div>
        <div class="detail-actions">
          <QueueActionButton :ids="artistSongIds" variant="detail" />
        </div>
      </div>
      <SongTable
        :songs="artistSongs"
        :loading="artistSongsLoading"
        :show-artist="false"
        :show-year="false"
        :album-context="true"
        :group-by-album="true"
        @mark="handleMark"
        @favorite="handleFavorite"
        @delete="handleDelete"
        @edit="handleEdit"
      />
    </template>

    <!-- Artist list -->
    <template v-else>
      <div v-if="loading" class="list-loading">Loading…</div>
      <div v-else class="artist-list-scroll">
        <table class="artist-table">
          <thead>
            <tr>
              <th
                class="col-artist sortable"
                @click="cycleArtistSort('artist')"
              >
                Artist{{ artistSortIndicator('artist') }}
              </th>
              <th
                class="col-albums sortable"
                @click="cycleArtistSort('albums')"
              >
                Albums{{ artistSortIndicator('albums') }}
              </th>
              <th
                class="col-tracks sortable"
                @click="cycleArtistSort('tracks')"
              >
                Tracks{{ artistSortIndicator('tracks') }}
              </th>
              <th class="col-actions"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="artist in sortedArtists"
              :key="artist.artist"
              class="artist-row"
              @click="selectArtist(artist)"
              @contextmenu="onArtistContextMenu(artist, $event)"
            >
              <td class="col-artist">
                {{ artist.artist || '(Unknown Artist)' }}
              </td>
              <td class="col-albums">{{ artist.albumCount }}</td>
              <td class="col-tracks">{{ artist.trackCount }}</td>
              <td class="col-actions" @click.stop>
                <button
                  class="row-menu-btn"
                  title="Actions"
                  @click="onArtistContextMenu(artist, $event)"
                >
                  …
                </button>
              </td>
            </tr>
            <tr v-if="sortedArtists.length === 0">
              <td colspan="4" class="list-empty">No artists found.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <ItemContextMenu
      v-if="ctxMenu"
      :x="ctxMenu.x"
      :y="ctxMenu.y"
      :ids="ctxMenu.ids"
      @close="ctxMenu = null"
    />
  </div>
</template>

<style scoped lang="scss">
.artists-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.list-loading,
.list-empty {
  color: #555;
  text-align: center;
  padding: 2rem;
}

.artist-list-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.artist-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  color: #e0e0e0;

  th {
    text-align: left;
    padding: 0.4rem 0.75rem;
    color: #999;
    font-weight: 500;
    border-bottom: 1px solid #333;
    position: sticky;
    top: 0;
    background: #1a1a1a;
    z-index: 1;
    white-space: nowrap;

    &.sortable {
      cursor: pointer;
      user-select: none;

      &:hover {
        color: #ccc;
      }
    }
  }

  .col-artist {
    width: auto;
  }
  .col-albums,
  .col-tracks {
    width: 72px;
    text-align: right;
    color: #888;
  }
}

.artist-row {
  cursor: pointer;
  border-bottom: 1px solid #1e1e1e;

  td {
    padding: 0.45rem 0.75rem;
  }

  &:hover {
    background: #1e1e1e;

    .row-menu-btn {
      opacity: 1;
    }
  }
}

.col-actions {
  width: 32px;
  padding: 0 0.2rem;
  text-align: center;
  overflow: visible;
}

.row-menu-btn {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 1rem;
  line-height: 1;
  opacity: 0;

  &:hover {
    background: #333;
    color: #ccc;
  }

  @media (hover: none) {
    opacity: 1;
    color: #888;
  }
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

.detail-info {
  flex: 1;
}

.detail-name {
  font-weight: 700;
  font-size: 1rem;
  color: #e0e0e0;
}

.detail-meta {
  font-size: 0.8rem;
  color: #888;
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

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, RouterLink } from 'vue-router';
import type { Playlist, SmartSearch } from '@/types/music';

defineProps<{
  width: number;
  mobileOpen: boolean;
  navLinks: { to: string; label: string }[];
  playlists: Playlist[];
  smartSearches: SmartSearch[];
}>();

const emit = defineEmits<{
  'create-playlist': [];
  'create-smart-search': [];
  'drop-onto-playlist': [playlistId: number, songIds: number[]];
}>();

const route = useRoute();

const navDropTarget = ref<number | null>(null);

function onNavDragOver(playlistId: number, e: DragEvent) {
  if (e.dataTransfer?.types.includes('application/x-song-ids')) {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy';
    }
    navDropTarget.value = playlistId;
  }
}

function onNavDragLeave() {
  navDropTarget.value = null;
}

async function onNavDrop(playlistId: number, e: DragEvent) {
  e.preventDefault();
  navDropTarget.value = null;
  const songStr = e.dataTransfer?.getData('application/x-song-ids');
  if (!songStr) {
    return;
  }
  const songIds: number[] = JSON.parse(songStr);
  emit('drop-onto-playlist', playlistId, songIds);
}
</script>

<template>
  <nav
    class="music-nav"
    :class="{ 'mobile-open': mobileOpen }"
    :style="{ width: width + 'px' }"
  >
    <RouterLink
      v-for="link in navLinks"
      :key="link.to"
      :to="link.to"
      class="nav-link"
      active-class="nav-link--active"
    >
      {{ link.label }}
    </RouterLink>

    <div class="nav-section-label">
      Smart Searches
      <button
        class="nav-add-btn"
        title="New Smart Search"
        @click.stop="emit('create-smart-search')"
      >
        +
      </button>
    </div>
    <RouterLink
      v-for="sp in smartSearches"
      :key="'sp-' + sp.id"
      :to="{ path: '/remote/music/smartsearch', query: { id: sp.id } }"
      class="nav-link nav-link--playlist"
      :class="{
        'nav-link--active':
          route.path === '/remote/music/smartsearch' &&
          route.query.id == String(sp.id),
      }"
    >
      {{ sp.name }}
    </RouterLink>
    <div v-if="smartSearches.length === 0" class="nav-empty">
      No smart searches
    </div>

    <div class="nav-section-label">
      Playlists
      <button
        class="nav-add-btn"
        title="New Playlist"
        @click.stop="emit('create-playlist')"
      >
        +
      </button>
    </div>
    <div
      v-for="pl in playlists"
      :key="'pl-' + pl.id"
      class="nav-link-wrap"
      :class="{ 'nav-drop-target': navDropTarget === pl.id }"
      @dragover="onNavDragOver(pl.id, $event)"
      @dragleave="onNavDragLeave"
      @drop="onNavDrop(pl.id, $event)"
    >
      <RouterLink
        :to="{ path: '/remote/music/playlist', query: { id: pl.id } }"
        class="nav-link nav-link--playlist"
        :class="{
          'nav-link--active':
            route.path === '/remote/music/playlist' &&
            route.query.id == String(pl.id),
        }"
      >
        {{ pl.name }}
      </RouterLink>
    </div>
    <div v-if="playlists.length === 0" class="nav-empty">No playlists</div>
  </nav>
</template>

<style scoped lang="scss">
.music-nav {
  display: flex;
  flex-direction: column;
  // width set via inline style
  flex-shrink: 0;
  background: #161616;
  padding: 0.5rem 0;
  overflow-y: auto;
  min-width: 60px;
}

.nav-link {
  display: block;
  padding: 0.5rem 1rem;
  color: #aaa;
  text-decoration: none;
  font-size: 0.85rem;
  transition:
    background 0.15s,
    color 0.15s;

  &:hover {
    background: #222;
    color: #e0e0e0;
  }

  &--active {
    background: #1e3a5f;
    color: #90caf9;
  }
}

.nav-section-label {
  display: flex;
  align-items: center;
  padding: 0.5rem 0.75rem 0.2rem;
  font-size: 0.68rem;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 0.25rem;
}

.nav-add-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0 0.2rem;
  border-radius: 3px;

  &:hover {
    background: #333;
    color: #ccc;
  }
}

.nav-link-wrap {
  &.nav-drop-target > .nav-link {
    background: #1a3a5f;
    color: #90caf9;
  }
}

.nav-link--playlist {
  padding-left: 1.25rem;
  font-size: 0.82rem;
}

.nav-empty {
  padding: 0.25rem 1.25rem;
  font-size: 0.78rem;
  color: #444;
  font-style: italic;
}

$mobile-bp: 600px;

@media (max-width: $mobile-bp) {
  .music-nav {
    position: absolute;
    z-index: 200;
    top: 0;
    left: 0;
    bottom: 0;
    width: min(280px, 85vw) !important;
    overflow-y: auto;
    box-shadow: 4px 0 16px rgba(0, 0, 0, 0.6);
    transform: translateX(-100%);
    transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);

    &.mobile-open {
      transform: translateX(0);
    }
  }
}
</style>

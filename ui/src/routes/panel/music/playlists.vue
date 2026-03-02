<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import PanelList from '@/components/panel/PanelList.vue';
import ActionMenu from '@/components/panel/ActionMenu.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';
import type { ActionItem } from '@/components/panel/ActionMenu.vue';
import type { Playlist } from '@/types/music';

const router = useRouter();
const player = useMusicPlayer();

const playlists = ref<Playlist[]>([]);
const selectedIdx = ref(0);
const actionMenuRef = ref<InstanceType<typeof ActionMenu> | null>(null);
const actionTargetId = ref<number | null>(null);

onMounted(async () => {
  try {
    const r = await fetch('/music/playlists');
    if (r.ok) {
      playlists.value = (await r.json()) as Playlist[];
    }
  } catch {
    /* ignore */
  }
});

const items = computed<ListItem[]>(() =>
  playlists.value.map((p) => ({
    label: p.name,
    secondary: String(p.items.length),
    icon: '',
  }))
);

function onSelect(i: number) {
  const p = playlists.value[i];
  if (!p) {
    return;
  }
  router.push({
    path: '/panel/music/songs',
    query: { playlist: String(p.id) },
  });
}

function onAction(i: number) {
  actionTargetId.value = playlists.value[i]?.id ?? null;
  actionMenuRef.value?.show();
}

function onHeaderAction() {
  actionTargetId.value = null;
  actionMenuRef.value?.show();
}

const actionItems: ActionItem[] = [
  { key: 'enqueue', label: 'Enqueue' },
  { key: 'append', label: 'Append' },
  { key: 'replace', label: 'Replace' },
];

async function onActionSelect(key: string) {
  const id = actionTargetId.value;
  if (id == null) {
    return;
  }
  try {
    const r = await fetch(`/music/playlists/${id}/songs`);
    if (!r.ok) {
      return;
    }
    const songs = (await r.json()) as Array<{ id: number }>;
    const ids = songs.map((s) => s.id);
    if (key === 'enqueue') {
      player.enqueue(ids);
    } else if (key === 'append') {
      player.appendQueue(ids);
    } else if (key === 'replace') {
      player.replaceQueue(ids);
    }
  } catch {
    /* ignore */
  }
}
</script>

<template>
  <div class="page">
    <PanelList
      v-model="selectedIdx"
      :items="items"
      header-label="Playlists"
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

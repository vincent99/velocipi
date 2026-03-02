<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useMusicPlayer } from '@/composables/useMusicPlayer';
import PanelList from '@/components/panel/PanelList.vue';
import ActionMenu from '@/components/panel/ActionMenu.vue';
import type { ListItem } from '@/components/panel/PanelList.vue';
import type { ActionItem } from '@/components/panel/ActionMenu.vue';
import type { SmartSearch } from '@/types/music';

const router = useRouter();
const player = useMusicPlayer();

const searches = ref<SmartSearch[]>([]);
const selectedIdx = ref(0);
const actionMenuRef = ref<InstanceType<typeof ActionMenu> | null>(null);
const actionTargetId = ref<number | null>(null);

onMounted(async () => {
  try {
    const r = await fetch('/music/smartsearches');
    if (r.ok) {
      searches.value = (await r.json()) as SmartSearch[];
    }
  } catch {
    /* ignore */
  }
});

const items = computed<ListItem[]>(() =>
  searches.value.map((s) => ({
    label: s.name,
    secondary: '',
    icon: '',
  }))
);

function onSelect(i: number) {
  const s = searches.value[i];
  if (!s) {
    return;
  }
  router.push({
    path: '/panel/music/songs',
    query: { smartsearch: String(s.id) },
  });
}

function onAction(i: number) {
  actionTargetId.value = searches.value[i]?.id ?? null;
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
    const r = await fetch(`/music/smartsearches/${id}/songs`);
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
    /* ignore */
  }
}
</script>

<template>
  <div class="page">
    <PanelList
      v-model="selectedIdx"
      :items="items"
      header-label="Smart Searches"
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

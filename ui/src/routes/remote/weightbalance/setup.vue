<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { Layout } from '@/types/weightbalance';
import PeopleEditor from '@/components/weightbalance/setup/PeopleEditor.vue';
import LayoutList from '@/components/weightbalance/setup/LayoutList.vue';
import LayoutEditor from '@/components/weightbalance/setup/LayoutEditor.vue';

const layouts = ref<Layout[]>([]);
const selectedId = ref<string | null>(null);
const loading = ref(true);
const saving = ref(false);
const saved = ref(false);
const error = ref('');

onMounted(load);

async function load() {
  loading.value = true;
  try {
    const r = await fetch('/wb/layouts');
    layouts.value = r.ok ? await r.json() : [];
    selectedId.value = layouts.value[0]?.id ?? null;
  } catch (e: unknown) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
}

const selectedLayout = computed(
  () => layouts.value.find((l) => l.id === selectedId.value) ?? null
);

async function saveLayouts() {
  saving.value = true;
  error.value = '';
  saved.value = false;
  try {
    const r = await fetch('/wb/layouts', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(layouts.value),
    });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    saved.value = true;
    setTimeout(() => {
      saved.value = false;
    }, 3000);
  } catch (e: unknown) {
    error.value = 'Save failed: ' + String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="wb-setup">
    <PeopleEditor />

    <div class="layouts-section">
      <div class="layouts-header">
        <span class="section-title">Layouts</span>
        <div class="section-actions">
          <span v-if="saved" class="saved-msg">Saved ✓</span>
          <button
            type="button"
            class="save-btn"
            :disabled="saving || loading"
            @click="saveLayouts"
          >
            {{ saving ? 'Saving…' : 'Save Layouts' }}
          </button>
        </div>
      </div>
      <p v-if="error" class="error-msg">{{ error }}</p>

      <LayoutList
        v-if="!loading"
        v-model:layouts="layouts"
        v-model:selected-id="selectedId"
      />

      <LayoutEditor
        v-if="selectedLayout"
        :key="selectedLayout.id"
        :layout="selectedLayout"
      />
      <p v-else-if="!loading" class="hint">
        No layout selected — add one above.
      </p>
    </div>
  </div>
</template>

<style scoped lang="scss">
.wb-setup {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem 1.25rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  color: #e0e0e0;
}

.layouts-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.section-title {
  font-size: 0.95rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #e0e0e0;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.saved-msg {
  color: #4ade80;
  font-size: 0.8rem;
}

.error-msg {
  color: #f87171;
  font-size: 0.82rem;
}

.save-btn {
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  color: #fff;
  padding: 0.35rem 0.9rem;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: #2563eb;
  }

  &:disabled {
    opacity: 0.5;
  }
}

.hint {
  color: #666;
  font-size: 0.85rem;
}
</style>

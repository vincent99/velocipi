<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import type { Layout } from '@/types/weightbalance';
import LayoutList from '@/components/weightbalance/setup/LayoutList.vue';
import LayoutEditor from '@/components/weightbalance/setup/LayoutEditor.vue';

const router = useRouter();

const layouts = ref<Layout[]>([]);
const selectedId = ref<string | null>(null);
const loading = ref(true);
const saving = ref(false);
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

function blankLayout(): Layout {
  return {
    id: crypto.randomUUID(),
    name: 'New layout',
    emptyWeight: 0,
    emptyCG: 0,
    gearRetractionMoment: 0,
    maxTakeoffWeight: 0,
    maxLandingWeight: 0,
    maxZeroFuelWeight: 0,
    fuelWeightPerGallon: 6,
    reserveFuelGal: 0,
    forwardCGLimits: [],
    aftCGLimits: [],
    stations: [],
  };
}

function addLayout() {
  const l = blankLayout();
  layouts.value.push(l);
  selectedId.value = l.id;
}

function copyLayout() {
  const l = selectedLayout.value;
  if (!l) {
    return;
  }
  // l (and its nested arrays) are Vue reactive proxies -- structuredClone
  // can throw on those ("could not be cloned") depending on the engine, so
  // round-trip through JSON instead, which is proxy-transparent and plenty
  // for this plain-data shape.
  const copy: Layout = JSON.parse(JSON.stringify(l));
  copy.id = crypto.randomUUID();
  copy.name = l.name + ' copy';
  layouts.value.push(copy);
  selectedId.value = copy.id;
}

function removeLayout() {
  const l = selectedLayout.value;
  if (!l) {
    return;
  }
  const idx = layouts.value.findIndex((x) => x.id === l.id);
  if (idx < 0) {
    return;
  }
  layouts.value.splice(idx, 1);
  selectedId.value = layouts.value[0]?.id ?? null;
}

async function saveLayouts() {
  saving.value = true;
  error.value = '';
  try {
    const r = await fetch('/wb/layouts', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(layouts.value),
    });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    router.push('/remote/weightbalance');
  } catch (e: unknown) {
    error.value = 'Save failed: ' + String(e);
  } finally {
    saving.value = false;
  }
}

function cancel() {
  router.push('/remote/weightbalance');
}
</script>

<template>
  <div class="wb-setup">
    <div class="layouts-section">
      <span class="section-title">Layouts</span>
      <p v-if="error" class="error-msg">{{ error }}</p>

      <LayoutList
        v-if="!loading"
        :layouts="layouts"
        :selected-id="selectedId"
        @select="(id) => (selectedId = id)"
        @add="addLayout"
        @copy="copyLayout"
        @delete="removeLayout"
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

    <div class="bottom-bar">
      <button type="button" class="cancel-btn" @click="cancel">Cancel</button>
      <button
        type="button"
        class="save-btn"
        :disabled="saving || loading"
        @click="saveLayouts"
      >
        {{ saving ? 'Saving…' : 'Save' }}
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.wb-setup {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem 1.25rem 5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  color: #e0e0e0;
  position: relative;
}

.section-title {
  display: block;
  font-size: 0.95rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #e0e0e0;
  margin-bottom: 0.75rem;
}

.error-msg {
  color: #f87171;
  font-size: 0.82rem;
}

.hint {
  color: #666;
  font-size: 0.85rem;
}

.bottom-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 0.75rem 1.25rem;
  background: #1a1a1a;
  border-top: 1px solid #333;
}

.cancel-btn {
  background: none;
  border: 1px solid #555;
  border-radius: 4px;
  color: #ccc;
  padding: 0.5rem 1.1rem;
  font-size: 0.88rem;
  cursor: pointer;

  &:hover {
    border-color: #888;
    color: #fff;
  }
}

.save-btn {
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  color: #fff;
  padding: 0.5rem 1.3rem;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: #2563eb;
  }

  &:disabled {
    opacity: 0.5;
  }
}
</style>

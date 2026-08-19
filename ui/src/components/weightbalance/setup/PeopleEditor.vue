<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { Person } from '@/types/weightbalance';

const people = ref<Person[]>([]);
const loading = ref(true);
const saving = ref(false);
const saved = ref(false);
const error = ref('');

onMounted(load);

async function load() {
  loading.value = true;
  try {
    const r = await fetch('/wb/people');
    people.value = r.ok ? await r.json() : [];
  } catch (e: unknown) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
}

function addPerson() {
  people.value.push({ id: crypto.randomUUID(), name: '', weight: 170 });
}

function removePerson(idx: number) {
  people.value.splice(idx, 1);
}

async function save() {
  saving.value = true;
  error.value = '';
  saved.value = false;
  try {
    const r = await fetch('/wb/people', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(people.value),
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
  <div class="people-editor">
    <div class="section-header">
      <span class="section-title">People</span>
      <div class="section-actions">
        <span v-if="saved" class="saved-msg">Saved ✓</span>
        <button type="button" class="save-btn" :disabled="saving" @click="save">
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
      </div>
    </div>
    <p v-if="error" class="error-msg">{{ error }}</p>

    <div v-if="!loading" class="people-table">
      <div class="table-head">
        <span>Name</span>
        <span>Weight (lb)</span>
        <span></span>
      </div>
      <div v-for="(p, idx) in people" :key="p.id" class="table-row">
        <input
          v-model="p.name"
          type="text"
          class="cell-input"
          placeholder="Name"
        />
        <input
          v-model.number="p.weight"
          type="number"
          min="0"
          class="cell-input weight-input"
        />
        <button type="button" class="delete-btn" @click="removePerson(idx)">
          Delete
        </button>
      </div>
      <p v-if="people.length === 0" class="hint">No people saved yet.</p>
      <button type="button" class="add-btn" @click="addPerson">
        + Add Person
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.people-editor {
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1rem 1.25rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.section-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #e0e0e0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
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

.table-head {
  display: grid;
  grid-template-columns: 2fr 1fr auto;
  gap: 0.75rem;
  color: #888;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid #333;
}

.table-row {
  display: grid;
  grid-template-columns: 2fr 1fr auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #262626;
}

.cell-input {
  background: none;
  border: none;
  border-bottom: 1px solid #444;
  color: #60a5fa;
  font-weight: 600;
  padding: 0.2rem 0;
  font-size: 0.9rem;

  &:focus {
    outline: none;
    border-color: #3b82f6;
  }
}

.weight-input {
  max-width: 100px;
}

.delete-btn {
  background: none;
  border: none;
  color: #f87171;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    color: #fca5a5;
  }
}

.hint {
  color: #666;
  font-size: 0.82rem;
  padding: 0.75rem 0;
}

.add-btn {
  background: none;
  border: none;
  color: #3b82f6;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.6rem 0 0.2rem;

  &:hover {
    color: #60a5fa;
  }
}
</style>

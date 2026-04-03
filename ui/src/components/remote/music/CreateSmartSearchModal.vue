<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{
  'update:show': [value: boolean];
  created: [];
}>();

const name = ref('');
const query = ref('');
const creating = ref(false);
const nameInput = ref<HTMLInputElement | null>(null);

watch(
  () => props.show,
  (open) => {
    if (open) {
      name.value = '';
      query.value = '';
      nextTick(() => nameInput.value?.focus());
    }
  }
);

async function create() {
  const trimmedName = name.value.trim();
  const trimmedQuery = query.value.trim();
  if (!trimmedName || !trimmedQuery) {
    return;
  }
  creating.value = true;
  try {
    const r = await fetch('/music/smartsearches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: trimmedName, query: trimmedQuery }),
    });
    if (r.ok) {
      emit('update:show', false);
      emit('created');
    }
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="modal-overlay"
      @click.self="emit('update:show', false)"
    >
      <div class="create-pl-modal create-pl-modal--wide">
        <div class="create-pl-title">New Smart Search</div>
        <input
          ref="nameInput"
          v-model="name"
          class="create-pl-input"
          type="text"
          placeholder="Name"
          @keydown.enter="create"
          @keydown.esc="emit('update:show', false)"
        />
        <textarea
          v-model="query"
          class="create-pl-textarea"
          placeholder="WHERE clause, e.g. plays > 5"
          rows="3"
          spellcheck="false"
          @keydown.esc="emit('update:show', false)"
        />
        <div class="create-sp-hint">
          <strong>Available fields:</strong>
          <code>title</code>, <code>artist</code>, <code>album</code>,
          <code>year</code>, <code>length</code> (seconds), <code>plays</code>,
          <code>marked</code> (0 or 1), <code>trackNumber</code>,
          <code>discNumber</code>, <code>format</code>,
          <code>bitrate</code> (kbps)<br />
          <strong>Examples:</strong>
          <code>plays &gt; 10</code> ·
          <code>length &gt; 300 AND year &gt;= 1990</code> ·
          <code>artist = 'Radiohead'</code> ·
          <code>marked = 1</code>
        </div>
        <div class="create-pl-actions">
          <button class="create-pl-cancel" @click="emit('update:show', false)">
            Cancel
          </button>
          <button
            class="create-pl-ok"
            :disabled="!name.trim() || !query.trim() || creating"
            @click="create"
          >
            {{ creating ? 'Creating…' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 600;
}

.create-pl-modal {
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  min-width: 280px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.7);
}

.create-pl-modal--wide {
  min-width: 380px;
  max-width: 520px;
  width: 90vw;
}

.create-pl-title {
  font-weight: 600;
  font-size: 0.95rem;
  margin-bottom: 0.75rem;
  color: #e0e0e0;
}

.create-pl-input {
  width: 100%;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.9rem;
  padding: 0.4rem 0.6rem;
  outline: none;
  box-sizing: border-box;

  &:focus {
    border-color: #3b82f6;
  }
}

.create-pl-textarea {
  width: 100%;
  margin-top: 0.5rem;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.88rem;
  font-family: 'Roboto Mono', 'Consolas', monospace;
  padding: 0.4rem 0.6rem;
  outline: none;
  resize: vertical;
  box-sizing: border-box;

  &:focus {
    border-color: #3b82f6;
  }
}

.create-sp-hint {
  margin-top: 0.6rem;
  font-size: 0.75rem;
  color: #777;
  line-height: 1.5;

  strong {
    color: #999;
  }

  code {
    background: #333;
    border-radius: 3px;
    padding: 0.05em 0.3em;
    font-size: 0.85em;
    color: #c8c8c8;
    font-family: 'Roboto Mono', 'Consolas', monospace;
  }
}

.create-pl-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.create-pl-cancel {
  background: none;
  border: 1px solid #444;
  color: #aaa;
  border-radius: 4px;
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
  cursor: pointer;

  &:hover {
    background: #333;
    color: #ccc;
  }
}

.create-pl-ok {
  background: #1e3a5f;
  border: 1px solid #2a5a9f;
  color: #90caf9;
  border-radius: 4px;
  padding: 0.3rem 0.75rem;
  font-size: 0.85rem;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: #2a4a7f;
    color: #fff;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}
</style>

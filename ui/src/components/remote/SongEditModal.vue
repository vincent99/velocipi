<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { Song } from '@/types/music';

interface Props {
  songs: Song[]; // one or more songs to edit
  saving?: boolean;
}

const props = withDefaults(defineProps<Props>(), { saving: false });

const emit = defineEmits<{
  save: [ids: number[], fields: Record<string, unknown>];
  cancel: [];
}>();

const multi = computed(() => props.songs.length > 1);

// For each editable field, track:
//  - the current form value (string representation)
//  - whether the checkbox is checked (multi-mode only)
//  - whether the values across the selected songs conflict
type FieldKey =
  | 'title'
  | 'artist'
  | 'album'
  | 'artistSort'
  | 'albumSort'
  | 'trackNumber'
  | 'trackTotal'
  | 'discNumber'
  | 'year'
  | 'genre';

interface FieldState {
  value: string | number;
  checked: boolean; // only meaningful in multi-mode
  conflict: boolean; // values differ across selected songs
}

function initialValue(key: FieldKey): string {
  if (props.songs.length === 0) {
    return '';
  }
  const first = props.songs[0];
  switch (key) {
    case 'title':
      return first.title;
    case 'artist':
      return first.artist;
    case 'album':
      return first.album;
    case 'artistSort':
      return first.artistSort;
    case 'albumSort':
      return first.albumSort;
    case 'trackNumber':
      return first.trackNumber > 0 ? String(first.trackNumber) : '';
    case 'trackTotal':
      return first.trackTotal > 0 ? String(first.trackTotal) : '';
    case 'discNumber':
      return first.discNumber > 0 ? String(first.discNumber) : '';
    case 'year':
      return first.year > 0 ? String(first.year) : '';
    case 'genre':
      return (first.genre ?? []).join(', ');
  }
}

function hasConflict(key: FieldKey): boolean {
  if (props.songs.length <= 1) {
    return false;
  }
  const _first = initialValue(key); // used only for default clause below
  return props.songs.some((s) => {
    switch (key) {
      case 'title':
        return s.title !== props.songs[0].title;
      case 'artist':
        return s.artist !== props.songs[0].artist;
      case 'album':
        return s.album !== props.songs[0].album;
      case 'artistSort':
        return s.artistSort !== props.songs[0].artistSort;
      case 'albumSort':
        return s.albumSort !== props.songs[0].albumSort;
      case 'trackNumber':
        return s.trackNumber !== props.songs[0].trackNumber;
      case 'trackTotal':
        return s.trackTotal !== props.songs[0].trackTotal;
      case 'discNumber':
        return s.discNumber !== props.songs[0].discNumber;
      case 'year':
        return s.year !== props.songs[0].year;
      case 'genre':
        return JSON.stringify(s.genre) !== JSON.stringify(props.songs[0].genre);
      default:
        return _first !== _first; // never
    }
  });
}

const FIELDS: FieldKey[] = [
  'title',
  'artist',
  'album',
  'artistSort',
  'albumSort',
  'trackNumber',
  'trackTotal',
  'discNumber',
  'year',
  'genre',
];

const fieldStates = ref<Record<FieldKey, FieldState>>(
  Object.fromEntries(
    FIELDS.map((k) => [
      k,
      {
        value: hasConflict(k) ? '' : initialValue(k),
        checked: false,
        conflict: hasConflict(k),
      },
    ])
  ) as Record<FieldKey, FieldState>
);

// Re-initialise whenever the song list changes (modal re-open).
watch(
  () => props.songs,
  () => {
    for (const k of FIELDS) {
      fieldStates.value[k] = {
        value: hasConflict(k) ? '' : initialValue(k),
        checked: false,
        conflict: hasConflict(k),
      };
    }
  },
  { deep: true }
);

const fieldLabels: Record<FieldKey, string> = {
  title: 'Title',
  artist: 'Artist',
  album: 'Album',
  artistSort: 'Artist Sort',
  albumSort: 'Album Sort',
  trackNumber: 'Track #',
  trackTotal: 'Track Total',
  discNumber: 'Disc #',
  year: 'Year',
  genre: 'Genre',
};

const numericFields = new Set<FieldKey>([
  'trackNumber',
  'trackTotal',
  'discNumber',
  'year',
]);

function placeholder(key: FieldKey): string {
  if (
    multi.value &&
    fieldStates.value[key].conflict &&
    !fieldStates.value[key].checked
  ) {
    return '—';
  }
  return '';
}

function handleSave() {
  const fields: Record<string, unknown> = {};

  for (const k of FIELDS) {
    // In multi mode only include checked fields; in single mode include all.
    if (multi.value && !fieldStates.value[k].checked) {
      continue;
    }

    const raw = String(fieldStates.value[k].value).trim();
    if (k === 'genre') {
      fields[k] = raw
        ? raw
            .split(',')
            .map((g) => g.trim())
            .filter(Boolean)
        : [];
    } else if (numericFields.has(k)) {
      const n = parseInt(raw, 10);
      fields[k] = isNaN(n) ? 0 : n;
    } else {
      fields[k] = raw;
    }
  }

  emit(
    'save',
    props.songs.map((s) => s.id),
    fields
  );
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click.self="emit('cancel')">
      <div class="modal-box">
        <div class="modal-header">
          <span v-if="multi">Edit {{ songs.length }} songs</span>
          <span v-else>Edit song</span>
          <button class="modal-close" @click="emit('cancel')">✕</button>
        </div>

        <div class="modal-body">
          <p v-if="multi" class="multi-hint">
            Check a field to write it to all {{ songs.length }} selected songs.
            An em-dash (—) means the values differ across the selection.
          </p>

          <div class="field-grid">
            <template v-for="key in FIELDS" :key="key">
              <!-- Checkbox (multi-mode only) -->
              <div class="field-check">
                <input
                  v-if="multi"
                  :id="`edit-chk-${key}`"
                  v-model="fieldStates[key].checked"
                  type="checkbox"
                />
              </div>

              <label
                :for="multi ? `edit-chk-${key}` : `edit-${key}`"
                class="field-label"
              >
                {{ fieldLabels[key] }}
              </label>

              <input
                :id="`edit-${key}`"
                v-model="fieldStates[key].value"
                class="field-input"
                :class="{
                  disabled: multi && !fieldStates[key].checked,
                  conflict:
                    fieldStates[key].conflict && !fieldStates[key].checked,
                }"
                :type="numericFields.has(key) ? 'number' : 'text'"
                :placeholder="placeholder(key)"
                :disabled="multi && !fieldStates[key].checked"
              />
            </template>
          </div>
        </div>

        <div class="modal-footer">
          <span v-if="multi" class="footer-count">
            {{ songs.length }} songs selected
          </span>
          <div class="footer-actions">
            <button class="btn-cancel" @click="emit('cancel')">Cancel</button>
            <button class="btn-save" :disabled="saving" @click="handleSave">
              <span v-if="saving" class="btn-spinner" aria-hidden="true" />
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-box {
  background: #1e1e1e;
  border: 1px solid #444;
  border-radius: 8px;
  width: min(520px, 95vw);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.8);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #333;
  font-weight: 600;
  color: #e0e0e0;
  font-size: 0.95rem;
  flex-shrink: 0;
}

.modal-close {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  font-size: 0.9rem;
  padding: 0.2rem 0.4rem;
  border-radius: 3px;

  &:hover {
    background: #333;
    color: #ccc;
  }
}

.modal-body {
  padding: 0.75rem 1rem;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.multi-hint {
  font-size: 0.78rem;
  color: #888;
  margin: 0 0 0.75rem;
}

.field-grid {
  display: grid;
  grid-template-columns: 20px 110px 1fr;
  gap: 0.35rem 0.5rem;
  align-items: center;
}

.field-check {
  display: flex;
  align-items: center;
  justify-content: center;

  input[type='checkbox'] {
    cursor: pointer;
    accent-color: #3b82f6;
  }
}

.field-label {
  font-size: 0.82rem;
  color: #aaa;
  white-space: nowrap;
}

.field-input {
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.85rem;
  padding: 0.3rem 0.5rem;
  width: 100%;
  box-sizing: border-box;
  outline: none;

  &:focus {
    border-color: #3b82f6;
  }

  &.disabled {
    color: #555;
    background: #222;
    border-color: #333;
    cursor: not-allowed;
  }

  &::placeholder {
    color: #555;
  }

  // Hide number spinner arrows for cleanliness
  &[type='number'] {
    -moz-appearance: textfield;

    &::-webkit-inner-spin-button,
    &::-webkit-outer-spin-button {
      -webkit-appearance: none;
    }
  }
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 1rem;
  border-top: 1px solid #333;
  flex-shrink: 0;
  gap: 0.5rem;
}

.footer-count {
  font-size: 0.8rem;
  color: #888;
}

.footer-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}

.btn-cancel {
  background: #333;
  border: 1px solid #555;
  border-radius: 4px;
  color: #ccc;
  padding: 0.35rem 0.9rem;
  font-size: 0.85rem;
  cursor: pointer;

  &:hover {
    background: #444;
    color: #fff;
  }
}

.btn-save {
  background: #3b82f6;
  border: 1px solid #2563eb;
  border-radius: 4px;
  color: #fff;
  padding: 0.35rem 0.9rem;
  font-size: 0.85rem;
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.4rem;

  &:hover:not(:disabled) {
    background: #2563eb;
  }

  &:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }
}

.btn-spinner {
  display: inline-block;
  width: 0.75em;
  height: 0.75em;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

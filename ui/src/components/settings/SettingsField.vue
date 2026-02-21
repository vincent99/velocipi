<script setup lang="ts">
import { inject } from 'vue';
import { settingsKey } from './settingsContext';

const props = defineProps<{
  label: string;
  path: string;
  type?: 'text' | 'number' | 'checkbox' | 'color';
  placeholder?: string;
  min?: number;
  max?: number;
}>();

const ctx = inject(settingsKey)!;
const type = props.type ?? 'text';

function onInput(e: Event) {
  const el = e.target as HTMLInputElement;
  if (type === 'number') {
    ctx.setPath(props.path, Number(el.value));
  } else if (type === 'checkbox') {
    ctx.setPath(props.path, el.checked);
  } else {
    ctx.setPath(props.path, el.value);
  }
}
</script>

<template>
  <div class="sf-row" :class="{ modified: ctx.isModified(path) }">
    <button
      v-if="ctx.isModified(path)"
      type="button"
      class="sf-reset"
      title="Reset to default"
      @click="ctx.reset(path)"
    >
      <i class="fi-sr-rotate-left" />
    </button>
    <span v-else class="sf-reset-placeholder" />

    <label class="sf-label">{{ label }}</label>

    <template v-if="type === 'color'">
      <div class="sf-color-wrap">
        <input
          :value="ctx.getPath(path) as string"
          type="color"
          class="sf-color-swatch"
          @input="onInput"
        />
        <input
          :value="ctx.getPath(path) as string"
          type="text"
          class="sf-input"
          :placeholder="placeholder"
          @input="onInput"
        />
      </div>
    </template>
    <template v-else-if="type === 'checkbox'">
      <input
        :checked="ctx.getPath(path) as boolean"
        type="checkbox"
        class="sf-checkbox"
        @change="onInput"
      />
    </template>
    <template v-else>
      <input
        :value="ctx.getPath(path) as string | number"
        :type="type"
        class="sf-input"
        :placeholder="placeholder"
        :min="min"
        :max="max"
        @input="onInput"
      />
    </template>
  </div>
</template>

<style scoped lang="scss">
.sf-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  min-width: 0; // prevents flex children from overflowing a grid cell

  &:last-child { margin-bottom: 0; }
}

.sf-reset,
.sf-reset-placeholder {
  width: 1.4rem;
  flex-shrink: 0;
}

.sf-reset {
  background: none;
  border: none;
  color: #3b82f6;
  cursor: pointer;
  padding: 0;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover { color: #60a5fa; }
}

.sf-label {
  width: 100px;
  flex-shrink: 0;
  color: #aaa;
  font-size: 0.85rem;

  .modified & {
    font-weight: 700;
    color: #3b82f6;
  }
}

.sf-input {
  flex: 1;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.3rem 0.5rem;
  font-size: 0.85rem;
  font-family: monospace;
  min-width: 0;

  &:focus { outline: none; border-color: #666; }
}

.sf-checkbox {
  width: 1.1rem;
  height: 1.1rem;
  cursor: pointer;
  accent-color: #3b82f6;
}

.sf-color-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.sf-color-swatch {
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
}
</style>

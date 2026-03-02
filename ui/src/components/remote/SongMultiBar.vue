<script setup lang="ts">
import { ref } from 'vue';

interface Props {
  count: number;
  isAdmin: boolean;
  playlistMode: boolean;
}

defineProps<Props>();

const emit = defineEmits<{
  enqueue: [];
  append: [];
  replace: [];
  mark: [marked: boolean];
  favorite: [fav: boolean];
  edit: [];
  delete: [];
  'remove-from-playlist': [];
  clear: [];
}>();

const multiMenuOpen = ref(false);

function doEmit(fn: () => void) {
  multiMenuOpen.value = false;
  fn();
}
</script>

<template>
  <Teleport to="body">
    <Transition name="float-bar">
      <div v-if="count > 1" class="multi-select-bar">
        <!-- Row 1: count + close (always one line) -->
        <div class="multi-top-row">
          <span class="multi-count">{{ count }} songs selected</span>
          <button
            class="multi-close"
            title="Clear selection"
            @click="emit('clear')"
          >
            ✕
          </button>
        </div>
        <!-- Row 2: action buttons -->
        <div class="multi-actions">
          <button @click="emit('enqueue')">Queue Next</button>
          <button @click="emit('append')">Queue Later</button>
          <button @click="emit('replace')">Play Now</button>
          <button
            class="multi-menu-btn"
            @click="multiMenuOpen = !multiMenuOpen"
          >
            More ▾
          </button>
          <div v-if="multiMenuOpen" class="multi-menu" @click.stop>
            <button @click="doEmit(() => emit('edit'))">Edit all</button>
            <button @click="doEmit(() => emit('mark', true))">Mark all</button>
            <button @click="doEmit(() => emit('mark', false))">
              Unmark all
            </button>
            <button @click="doEmit(() => emit('favorite', true))">
              Favorite all
            </button>
            <button @click="doEmit(() => emit('favorite', false))">
              Unfavorite all
            </button>
            <template v-if="playlistMode">
              <hr />
              <button @click="doEmit(() => emit('remove-from-playlist'))">
                Remove from Playlist
              </button>
            </template>
            <template v-else-if="isAdmin">
              <hr />
              <button class="menu-danger" @click="doEmit(() => emit('delete'))">
                Delete all
              </button>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.multi-select-bar {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  background: #1e3a5f;
  border: 1px solid #2a5a9f;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.7);
  z-index: 300;
  white-space: nowrap;
  color: #90caf9;
  font-size: 0.85rem;
}

.multi-top-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.multi-count {
  font-weight: 600;
  flex: 1;
}

.multi-actions {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  position: relative;
  flex-wrap: wrap;

  button {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    color: #90caf9;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;

    &:hover {
      background: rgba(255, 255, 255, 0.2);
      color: #fff;
    }
  }
}

.multi-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.25rem 0;
  z-index: 310;
  min-width: 140px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);

  button {
    display: block;
    width: 100%;
    background: none !important;
    border: none !important;
    color: #e0e0e0 !important;
    padding: 0.4rem 0.75rem;
    text-align: left;
    font-size: 0.85rem;
    cursor: pointer;
    border-radius: 0 !important;

    &:hover {
      background: #3b82f6 !important;
      color: #fff !important;
    }

    &.menu-danger {
      color: #f87171 !important;

      &:hover {
        background: #7f1d1d !important;
        color: #fca5a5 !important;
      }
    }
  }

  hr {
    border: none;
    border-top: 1px solid #444;
    margin: 0.25rem 0;
  }
}

.multi-close {
  background: none;
  border: none;
  color: #90caf9;
  cursor: pointer;
  padding: 0.2rem 0.3rem;
  font-size: 0.8rem;
  border-radius: 3px;
  flex-shrink: 0;

  &:hover {
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
  }
}

.float-bar-enter-active,
.float-bar-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.float-bar-enter-from,
.float-bar-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(6px);
}

@media (max-width: 600px) {
  .multi-select-bar {
    width: min(92vw, 420px);
    bottom: 1rem;
  }
}
</style>

<script setup lang="ts">
import { RouterView } from 'vue-router';
import SessionSidebar from '@/components/SessionSidebar.vue';
import { useTranscriptFeed } from '@/composables/useTranscriptFeed';
import { useAudioPlayer } from '@/composables/useAudioPlayer';

const { connected } = useTranscriptFeed();
const { unlocked, autoplayEnabled, enableSound } = useAudioPlayer();
</script>

<template>
  <div class="app">
    <header class="topbar">
      <h1>liveatc</h1>
      <span class="conn" :class="{ on: connected }">
        {{ connected ? 'live feed connected' : 'feed offline' }}
      </span>

      <div class="topbar-right">
        <button v-if="!unlocked" class="btn sound-btn" @click="enableSound">
          🔊 Enable sound
        </button>
        <label v-else class="autoplay-toggle">
          <input type="checkbox" v-model="autoplayEnabled" />
          Auto-play new transmissions
        </label>
      </div>
    </header>
    <div class="body">
      <SessionSidebar />
      <main class="main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

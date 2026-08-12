import { ref, watch } from 'vue';

// A single shared <audio> element: only one clip plays at a time, and any part
// of the app can see whether audio is currently playing (used to gate live
// auto-play so a new transmission never talks over one you're listening to).
const audio = typeof Audio !== 'undefined' ? new Audio() : null;
const currentId = ref<string | null>(null);
const playing = ref(false);

// unlocked: whether the browser will let us start playback programmatically.
// Browsers block audio until the user interacts with the page, so this starts
// false and flips true after the first successful play (a Listen click, or the
// header's "Enable sound" button). It is per page-load, not persisted.
const unlocked = ref(false);

// autoplayEnabled: user preference (persisted) for auto-playing new live
// transmissions. Only meaningful once unlocked. Defaults on.
const AUTOPLAY_KEY = 'liveatc.autoplay';
function readAutoplayPref(): boolean {
  try {
    const v = localStorage.getItem(AUTOPLAY_KEY);
    return v === null ? true : v === '1';
  } catch {
    return true;
  }
}
const autoplayEnabled = ref(readAutoplayPref());
watch(autoplayEnabled, (v) => {
  try {
    localStorage.setItem(AUTOPLAY_KEY, v ? '1' : '0');
  } catch {
    /* ignore storage errors */
  }
});

// A valid, zero-length WAV used to "prime" the shared element inside a user
// gesture so later programmatic plays are allowed (Safari needs the first play
// to originate from a gesture on the element itself).
const SILENT_WAV =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=';

if (audio) {
  // Only "ended"/"error" clear the playing state -- deliberately not "pause",
  // because swapping src to start a new clip fires a spurious pause we don't
  // want to treat as "stopped".
  const clear = () => {
    playing.value = false;
    currentId.value = null;
  };
  audio.addEventListener('ended', clear);
  audio.addEventListener('error', clear);
}

let loadedUrl = '';

// play starts a clip from the beginning, replacing whatever was playing. It sets
// playing=true synchronously so a same-tick auto-play guard sees it immediately.
function play(id: string, url: string): void {
  if (!audio) return;
  if (loadedUrl !== url) {
    audio.src = url;
    loadedUrl = url;
  }
  audio.currentTime = 0;
  currentId.value = id;
  playing.value = true;
  audio.play().then(
    () => {
      unlocked.value = true;
    },
    () => {
      // Autoplay may be blocked until the user has interacted with the page;
      // reset so the UI doesn't show a stuck "playing" state.
      if (currentId.value === id) {
        playing.value = false;
        currentId.value = null;
      }
    }
  );
}

// tryAutoplay plays only when unlocked, the preference is on, and nothing is
// currently playing. Returns whether it actually started.
function tryAutoplay(id: string, url: string): boolean {
  if (!audio || !unlocked.value || !autoplayEnabled.value || playing.value) {
    return false;
  }
  play(id, url);
  return true;
}

// enableSound primes the shared element within a user gesture (the header
// button's click), unlocking later programmatic playback.
function enableSound(): void {
  if (!audio) {
    unlocked.value = true;
    return;
  }
  const prevMuted = audio.muted;
  audio.muted = true;
  audio.src = SILENT_WAV;
  loadedUrl = SILENT_WAV;
  const done = () => {
    audio.muted = prevMuted;
    unlocked.value = true;
  };
  audio.play().then(() => {
    audio.pause();
    done();
  }, done);
}

export function useAudioPlayer() {
  return {
    currentId,
    playing,
    unlocked,
    autoplayEnabled,
    play,
    tryAutoplay,
    enableSound,
  };
}

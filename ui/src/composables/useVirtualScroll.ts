import { ref, computed, onMounted, onUnmounted, watch, type Ref } from 'vue';
import type { Song } from '@/types/music';

const ROW_H = 29; // px — must match .vrow height in CSS
const ROW_H_MOBILE = 48; // px — must match .vrow height on mobile in CSS
const MOBILE_BP = 600; // px — must match $mobile-bp in SCSS
const OVERSCAN = 5;

export function useVirtualScroll(
  sortedSongs: () => Song[],
  resolvedSongs: () => Song[],
  songs: () => Song[], // watched to reset scroll on data change
  showArtist: () => boolean,
  showAlbum: () => boolean,
  showYear: () => boolean,
  albumContext: () => boolean,
  playlistMode: () => boolean,
  scrollEl: Ref<HTMLElement | null>,
  scrollTop: Ref<number>
) {
  const isMobile = ref(
    typeof window !== 'undefined' && window.innerWidth <= MOBILE_BP
  );
  let mobileMq: MediaQueryList | null = null;
  const viewportH = ref(400);

  function resetScroll() {
    if (scrollEl.value) {
      scrollEl.value.scrollTop = 0;
    }
    scrollTop.value = 0;
  }

  function onMobileChange(e: MediaQueryListEvent) {
    isMobile.value = e.matches;
    // Reset scroll when layout changes so spacer math stays correct
    resetScroll();
  }

  const effectiveRowH = computed(() => (isMobile.value ? ROW_H_MOBILE : ROW_H));

  function onScroll() {
    if (scrollEl.value) {
      scrollTop.value = scrollEl.value.scrollTop;
    }
  }

  let ro: ResizeObserver | null = null;

  onMounted(() => {
    if (scrollEl.value) {
      ro = new ResizeObserver((entries) => {
        viewportH.value = entries[0].contentRect.height;
      });
      ro.observe(scrollEl.value);
      viewportH.value = scrollEl.value.clientHeight;
    }
    mobileMq = window.matchMedia(`(max-width: ${MOBILE_BP}px)`);
    isMobile.value = mobileMq.matches;
    mobileMq.addEventListener('change', onMobileChange);
  });

  onUnmounted(() => {
    ro?.disconnect();
    mobileMq?.removeEventListener('change', onMobileChange);
  });

  // Reset scroll position when songs list changes (e.g. new search results)
  watch(
    () => songs(),
    () => {
      resetScroll();
    }
  );

  const visibleRange = computed(() => {
    const total = sortedSongs().length;
    const rowH = effectiveRowH.value;
    const first = Math.max(0, Math.floor(scrollTop.value / rowH) - OVERSCAN);
    const visibleCount = Math.ceil(viewportH.value / rowH) + OVERSCAN * 2;
    const last = Math.min(total - 1, first + visibleCount);
    return { first, last };
  });

  const visibleSongs = computed(() =>
    resolvedSongs().slice(visibleRange.value.first, visibleRange.value.last + 1)
  );

  const spacerTop = computed(
    () => visibleRange.value.first * effectiveRowH.value
  );

  const spacerBottom = computed(
    () =>
      (sortedSongs().length - 1 - visibleRange.value.last) * effectiveRowH.value
  );

  // Grid template columns for the flat virtual list
  const gridCols = computed(() => {
    // Mobile: check | cover | info | actions (artist/album/num hidden via CSS)
    if (isMobile.value) {
      return '28px 44px 1fr 36px';
    }
    const cols: string[] = [];
    if (playlistMode()) {
      cols.push('20px'); // drag handle
    }
    cols.push('28px'); // checkbox
    if (showArtist()) {
      cols.push('minmax(80px, 1.5fr)');
    }
    if (showAlbum()) {
      cols.push('minmax(80px, 1.5fr)');
    }
    if (albumContext()) {
      cols.push('50px'); // track before title
    }
    cols.push('minmax(100px, 2fr)'); // title
    if (!albumContext()) {
      cols.push('60px'); // track after title
    }
    cols.push('56px'); // duration
    if (showYear()) {
      cols.push('48px');
    }
    cols.push('36px'); // actions
    return cols.join(' ');
  });

  return {
    isMobile,
    visibleRange,
    visibleSongs,
    spacerTop,
    spacerBottom,
    gridCols,
    onScroll,
  };
}

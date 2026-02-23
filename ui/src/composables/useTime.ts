import { ref, onMounted, onUnmounted } from 'vue';
import type { Ref } from 'vue';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import type { TimeFormat } from '@/types/config';

dayjs.extend(utc);
dayjs.extend(timezone);

/**
 * Format a UTC Date in a fixed UTC display: HH:mm:ss
 */
export function formatUtcClock(d: Date): string {
  return dayjs.utc(d).format('HH:mm:ss');
}

/**
 * Get the current time formatted for a given IANA timezone.
 * fmt is a dayjs format string (e.g. "hh:mm:ssa").
 * If allowSeconds is false, ':ss' is stripped from the format.
 */
export function formatTz(
  d: Date,
  tz: string,
  fmt: TimeFormat,
  allowSeconds = true
): string {
  const fmtStr = allowSeconds ? fmt : fmt.replace(':ss', '');
  return dayjs(d).tz(tz).format(fmtStr);
}

/**
 * useTime — provides a reactive `now` ref that ticks every second.
 * Use this once at the top of a component/page; pass `now` to formatTz / formatUtcClock.
 */
export function useTime(): { now: Ref<Date> } {
  const now = ref(new Date());
  let timer: ReturnType<typeof setInterval> | null = null;
  let alignTimeout: ReturnType<typeof setTimeout> | null = null;

  onMounted(() => {
    // Align to the next second boundary for clean ticking.
    const msToNextSecond = 1000 - (Date.now() % 1000);
    alignTimeout = setTimeout(() => {
      alignTimeout = null;
      now.value = new Date();
      timer = setInterval(() => {
        now.value = new Date();
      }, 1000);
    }, msToNextSecond);
  });

  onUnmounted(() => {
    if (alignTimeout !== null) {
      clearTimeout(alignTimeout);
    }
    if (timer !== null) {
      clearInterval(timer);
    }
  });

  return { now };
}

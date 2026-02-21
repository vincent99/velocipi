import type { InjectionKey } from 'vue';

export interface SettingsContext {
  isModified: (path: string) => boolean;
  reset: (path: string) => void;
  getPath: (path: string) => unknown;
  setPath: (path: string, value: unknown) => void;
}

export const settingsKey = Symbol() as InjectionKey<SettingsContext>;

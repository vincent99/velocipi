import type { PanelMeta } from '@/types/config';

export interface PanelRoute {
  path: string;
  name: string;
  icon: string;
  iconStyle: string;
  sort?: number;
}

const modules = import.meta.glob('../routes/panel/**/*.vue', { eager: true });

const routes: PanelRoute[] = Object.entries(modules)
  .filter(([file, mod]) => {
    // Only include top-level panel files (no subdirectory) that export panelMeta.
    const stripped = file
      .replace(/^\.\.\/routes\/panel\//, '')
      .replace(/\.vue$/, '')
      .replace(/\/index$/, '');
    if (stripped.includes('/')) {
      return false;
    }
    return !!(mod as { panelMeta?: PanelMeta }).panelMeta;
  })
  .map(([file, mod]) => {
    const stripped = file
      .replace(/^\.\.\/routes\/panel\//, '')
      .replace(/\.vue$/, '')
      .replace(/\/index$/, '');

    const path = '/panel/' + stripped;
    const meta = (mod as { panelMeta?: PanelMeta }).panelMeta!;

    return {
      path,
      name: meta.name,
      icon: meta.icon,
      iconStyle: meta.iconStyle ?? 'sr',
      sort: meta.sort ?? 0,
    };
  })
  .sort((a, b) => {
    if (a.sort !== b.sort) {
      return a.sort - b.sort;
    }
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });

export function usePanelRoutes(): PanelRoute[] {
  return routes;
}

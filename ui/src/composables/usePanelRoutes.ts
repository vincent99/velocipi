import type { PanelMeta } from '../types/config';

export interface PanelRoute {
  path: string;
  name: string;
  icon: string;
  sort?: number;
}

const modules = import.meta.glob('../routes/panel/**/*.vue', { eager: true });

const routes: PanelRoute[] = Object.entries(modules)
  .map(([file, mod]) => {
    const stripped = file
      .replace(/^\.\.\/routes\/panel\//, '')
      .replace(/\.vue$/, '')
      .replace(/\/index$/, '');

    const path = '/panel/' + stripped;
    const meta = (mod as { panelMeta?: PanelMeta }).panelMeta ?? {
      name: stripped,
      icon: '□',
    };

    return { path, name: meta.name, icon: meta.icon, sort: meta.sort ?? 0 };
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

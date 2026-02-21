import type { PanelMeta } from '@/types/config';

export interface RemoteRoute {
  path: string;
  name: string;
  icon: string;
  sort: number;
}

const modules = import.meta.glob('../routes/remote/**/*.vue', { eager: true });

const routes: RemoteRoute[] = Object.entries(modules)
  .map(([file, mod]) => {
    const stripped = file
      .replace(/^\.\.\/routes\/remote\//, '')
      .replace(/\.vue$/, '')
      .replace(/\/index$/, '');

    const path = '/remote/' + stripped;
    const meta = (mod as { remoteMeta?: PanelMeta }).remoteMeta ?? {
      name: stripped,
      icon: '□',
    };

    return { path, name: meta.name, icon: meta.icon, sort: meta.sort ?? 0 };
  })
  .sort((a, b) => {
    if (a.sort !== b.sort) return a.sort - b.sort;
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });

export function useRemoteRoutes(): RemoteRoute[] {
  return routes;
}

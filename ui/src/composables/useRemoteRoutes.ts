import type { PanelMeta } from '@/types/config';
import { useAdmin } from '@/composables/useAdmin';

export interface RemoteRoute {
  path: string;
  name: string;
  icon: string;
  sort: number;
  headerScreen: boolean;
}

const modules = import.meta.glob('../routes/remote/**/*.vue', { eager: true });

const { isAdmin } = useAdmin();

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

    if (meta.admin && !isAdmin) {
      return null;
    }

    return {
      path,
      name: meta.name,
      icon: meta.icon,
      sort: meta.sort ?? 0,
      headerScreen: meta.headerScreen ?? true,
    };
  })
  .filter((r): r is RemoteRoute => r !== null)
  .sort((a, b) => {
    if (a.sort !== b.sort) {
      return a.sort - b.sort;
    }
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });

export function useRemoteRoutes(): RemoteRoute[] {
  return routes;
}

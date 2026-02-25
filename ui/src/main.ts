import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import './style.scss';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/700.css';
import '@flaticon/flaticon-uicons/css/solid/rounded.css';
import '@flaticon/flaticon-uicons/css/regular/rounded.css';
import App from '@/App.vue';

const modules = import.meta.glob('./routes/**/*.vue');

// Bucket every discovered file by depth:
//   depth-0  → e.g. "remote"         (no slash)
//   depth-1  → e.g. "remote/music"   (one slash)
//   depth-2+ → e.g. "remote/music/songs"
const byPath: Record<string, () => Promise<unknown>> = {};
for (const [file, component] of Object.entries(modules)) {
  const stripped = file.replace(/^\.\/routes\//, '').replace(/\.vue$/, '');
  byPath[stripped] = component;
}

function buildChildren(
  parentPath: string,
  allPaths: Record<string, () => Promise<unknown>>
): RouteRecordRaw[] {
  const children: RouteRecordRaw[] = [];
  for (const [p, comp] of Object.entries(allPaths)) {
    // Direct child: starts with "parentPath/" and has no further slash after that
    if (!p.startsWith(parentPath + '/')) {
      continue;
    }
    const rest = p.slice(parentPath.length + 1);
    if (rest.includes('/')) {
      // deeper — skip here, will be handled recursively
      continue;
    }
    const grandchildren = buildChildren(p, allPaths);
    const route: RouteRecordRaw = { path: rest, component: comp };
    if (grandchildren.length > 0) {
      route.children = grandchildren;
    }
    children.push(route);
  }
  return children;
}

const routes: RouteRecordRaw[] = [];

if (byPath['index']) {
  routes.push({ path: '/', component: byPath['index'] });
} else {
  routes.push({ path: '/', redirect: '/remote/home' });
}

// Build top-level routes (no slash in key)
for (const [name, component] of Object.entries(byPath)) {
  if (name.includes('/') || name === 'index') {
    continue;
  }

  const children = buildChildren(name, byPath);

  if (name === 'panel') {
    children.unshift({ path: '', redirect: '/panel/home' });
  }
  if (name === 'remote') {
    children.unshift({ path: '', redirect: '/remote/home' });
  }

  routes.push({ path: '/' + name, component, children });
}

const router = createRouter({
  history: createWebHistory(),
  routes,
});

createApp(App).use(router).mount('#app');

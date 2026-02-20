import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import App from './App.vue';

const modules = import.meta.glob('./routes/**/*.vue');

const topLevel: Record<string, () => Promise<unknown>> = {};
const nested: Record<string, () => Promise<unknown>> = {};

for (const [file, component] of Object.entries(modules)) {
  const stripped = file.replace(/^\.\/routes\//, '').replace(/\.vue$/, '');
  if (stripped.includes('/')) {
    nested[stripped] = component;
  } else {
    topLevel[stripped] = component;
  }
}

const routes: RouteRecordRaw[] = [];

if (topLevel['index']) {
  routes.push({ path: '/', component: topLevel['index'] });
}

for (const [name, component] of Object.entries(topLevel)) {
  if (name === 'index') {
    continue;
  }

  const children: RouteRecordRaw[] = [];
  for (const [childStripped, childComponent] of Object.entries(nested)) {
    if (childStripped.startsWith(name + '/')) {
      const relative = childStripped
        .slice(name.length + 1)
        .replace(/\/index$/, '')
        .replace(/^index$/, '');
      children.push({ path: relative, component: childComponent });
    }
  }

  routes.push({ path: '/' + name, component, children });
}

const router = createRouter({
  history: createWebHistory(),
  routes,
});

createApp(App).use(router).mount('#app');

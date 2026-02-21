import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import './style.scss';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/700.css';
import '@flaticon/flaticon-uicons/css/solid/rounded.css';
import App from '@/App.vue';

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
} else {
  routes.push({ path: '/', redirect: '/remote/home' });
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

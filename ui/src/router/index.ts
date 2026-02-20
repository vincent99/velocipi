import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const modules = import.meta.glob('../routes/**/*.vue')

const routes: RouteRecordRaw[] = Object.entries(modules).map(([file, component]) => {
  // Strip prefix and .vue suffix: ../routes/panel/index.vue → panel/index
  const stripped = file.replace(/^\.\.\/routes\//, '').replace(/\.vue$/, '')
  // Remove trailing /index or replace bare index with empty string
  const path = '/' + stripped.replace(/\/index$/, '').replace(/^index$/, '')
  return { path, component }
})

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router

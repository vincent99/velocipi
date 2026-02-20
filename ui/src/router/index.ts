import { createRouter, createWebHistory } from 'vue-router'
import AdminView from '../views/AdminView.vue'
import AppView from '../views/AppView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: AdminView },
    { path: '/app', component: AppView },
  ],
})

export default router

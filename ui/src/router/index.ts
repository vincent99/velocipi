import { createRouter, createWebHistory } from 'vue-router'
import RemoteView from '../views/RemoteView.vue'
import PanelView from '../views/PanelView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: RemoteView },
    { path: '/panel', component: PanelView },
  ],
})

export default router

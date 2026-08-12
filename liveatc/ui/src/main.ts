import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import App from '@/App.vue';
import Home from '@/routes/home.vue';
import SessionView from '@/routes/session.vue';
import './style.scss';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/session/:id', component: SessionView, props: true },
  ],
});

createApp(App).use(router).mount('#app');

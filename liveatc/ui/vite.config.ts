import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

// The liveatc backend (intercom-stt) listens on :8090 by default. In dev the
// Vite server proxies API + websocket routes to it; in production the Go server
// serves the built dist/ directly (see internal/api spaHandler).
const backend = process.env.LIVEATC_BACKEND ?? 'localhost:8090';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 8091,
    proxy: {
      '/api': { target: `http://${backend}`, changeOrigin: false },
      '/ws': { target: `ws://${backend}`, ws: true, changeOrigin: false },
      '/healthz': { target: `http://${backend}`, changeOrigin: false },
    },
  },
});

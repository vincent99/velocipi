import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 8081,
    allowedHosts: true,
    // NOTE: every Go API route prefix must be listed here so the dev server
    // forwards it to Go instead of serving the SPA's index.html.
    proxy: {
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
        changeOrigin: false,
      },
      '/screen': {
        target: 'ws://localhost:8080',
        ws: true,
        changeOrigin: false,
      },
      '/config': {
        target: 'http://localhost:8080',
        changeOrigin: false,
      },
      '/cameras': {
        target: 'http://localhost:8080',
        changeOrigin: false,
      },
      '/hls': {
        target: 'http://localhost:8080',
        changeOrigin: false,
      },
      '/snapshot': {
        target: 'http://localhost:8080',
        changeOrigin: false,
        // Disable response buffering so multipart/x-mixed-replace frames
        // are forwarded to the browser as they arrive rather than being
        // held until the connection closes.
        selfHandleResponse: true,
        configure: (proxy) => {
          proxy.on(
            'proxyRes',
            (proxyRes, req, res: import('http').ServerResponse) => {
              // Copy status and headers through unchanged.
              res.writeHead(proxyRes.statusCode ?? 200, proxyRes.headers);
              // Pipe raw bytes directly — no buffering.
              proxyRes.pipe(res);
            }
          );
        },
      },
    },
  },
});

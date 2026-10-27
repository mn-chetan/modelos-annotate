import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig(() => {
  return {
    base: process.env.VITE_BASE || '/app1/',
    plugins: [react(), tailwindcss()],
    build: { rollupOptions: { input: { landing: 'index.html', landingAlias: 'landing.html', workspace: 'next.html' } } },
    resolve: {
      dedupe: ['react', 'react-dom', 'lucide-react'],
      alias: {
        '@': import.meta.dirname,
      },
    },
    server: {
      proxy: {
        // The production UI is mounted below /app1, so local requests use
        // /app1/api/v1. Strip the UI mount before forwarding to FastAPI's
        // canonical /api/v1 router.
        '/app1/api': {
          target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
          rewrite: (path) => path.replace(/^\/app1/, ''),
        },
        '/api': {
          target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
      },
      strictPort: true,
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
  };
});

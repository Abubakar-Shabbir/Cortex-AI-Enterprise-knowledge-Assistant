import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served by Django at /app/ in production (see RAG/spa_views.py) - the
// build output's asset URLs need that same base path so they resolve
// correctly once Django serves index.html from /app/.
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    port: 5173,
    // Same-origin-feeling dev setup without CORS: the SPA calls plain
    // '/api/...' paths (see src/api/client.js) and Vite forwards them
    // to Django's dev server. changeOrigin + the Django session/CSRF
    // cookies set for 127.0.0.1/localhost both keep working since the
    // browser only ever talks to this Vite origin.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
  },
})

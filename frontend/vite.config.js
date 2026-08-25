import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite is frontend-only: HMR + bundling. The SPA talks directly to
// Django at VITE_API_BASE_URL (see src/api/client.js) — no /api proxy.
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    // Pin hostname so it matches the Django API host (localhost, not
    // 127.0.0.1). Mixing them makes session cookies cross-site under
    // SameSite=Lax and login appears to work while /api/dashboard/ 403s.
    host: 'localhost',
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
  },
})

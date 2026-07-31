import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Dev server proxies API calls to the FastAPI backend so the browser talks to
// a single origin (no CORS juggling in development).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  // Tests live in tests/, mirroring src/ — same split as the backend's tests/
  // tree. src/ stays production code only.
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['./tests/setup.ts'],
    css: false,
  },
})

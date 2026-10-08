import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev, the UI runs on :5173 and forwards API calls to FastAPI (`api` service in docker compose).
const api = process.env.API_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    proxy: { '/api': api },
    // Inside docker compose, file events from the bind mount are unreliable: poll instead.
    watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 1000 } : undefined,
  },
})

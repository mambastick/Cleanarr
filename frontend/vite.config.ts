import { existsSync } from 'node:fs'
import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const repositoryBackend = path.resolve(import.meta.dirname, '../backend/src')
const backendSource = existsSync(repositoryBackend)
  ? repositoryBackend
  : path.resolve(import.meta.dirname, '../src')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      // Preserve the browser-facing Host header. CleanArr compares it with
      // Origin/Referer for cookie-authenticated mutations, including the
      // first-run registration request. Vite enables changeOrigin for string
      // targets, which would otherwise make every local mutation look
      // cross-origin to the API.
      "/api": { target: "http://127.0.0.1:8089", changeOrigin: false },
      "/health": { target: "http://127.0.0.1:8089", changeOrigin: false },
      "/webhook": { target: "http://127.0.0.1:8089", changeOrigin: false },
    },
  },
  build: {
    outDir: path.join(backendSource, 'cleanarr/ui/static'),
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
})

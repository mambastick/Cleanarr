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
      "/api": "http://127.0.0.1:8089",
      "/health": "http://127.0.0.1:8089",
      "/webhook": "http://127.0.0.1:8089",
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

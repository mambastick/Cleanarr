import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
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
    outDir: '../src/cleanarr/ui/static',
    emptyOutDir: true,
  },
})

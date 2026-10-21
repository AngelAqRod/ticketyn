import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readProjectVersion } from './config/projectVersion.ts'

// Resolve against this config file, not the shell cwd or installed Python metadata.
const projectVersion = readProjectVersion(new URL('../pyproject.toml', import.meta.url))

export default defineConfig({
  define: { __TICKETYN_FRONTEND_VERSION__: JSON.stringify(projectVersion) },
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist' },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    clearMocks: true,
  },
})

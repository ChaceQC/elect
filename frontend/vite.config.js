import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

export default defineConfig({
  plugins: [react(), {
    name: 'development-mock-worker', apply: 'serve',
    configureServer(server) {
      if (process.env.VITE_ENABLE_MSW !== 'true') return
      server.middlewares.use('/mockServiceWorker.js', (_request, response) => {
        response.setHeader('Content-Type', 'application/javascript')
        response.end(readFileSync(require.resolve('msw/mockServiceWorker.js')))
      })
    },
  }],
  base: '/',
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{js,jsx}'],
    setupFiles: ['tests/setup.js'],
  },
})

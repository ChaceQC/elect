import { setupWorker } from 'msw/browser'
import { handlersFor } from './handlers.js'

export async function startMocks() {
  if (!import.meta.env.DEV || import.meta.env.VITE_ENABLE_MSW !== 'true') return
  const worker = setupWorker(...handlersFor('empty_account'))
  await worker.start({ onUnhandledRequest: 'bypass' })
}

import { setupServer as createServer } from 'msw/node'
import { http, HttpResponse } from 'msw'

// 既有组件场景保留旧后端语义；R6专项显式覆盖新接口。
/** @param {Parameters<typeof createServer>} handlers */
export function setupServer(...handlers) {
  return createServer(...handlers, http.get('/api/v1/auth/session', () =>
    HttpResponse.json({ error: { code: 'NOT_FOUND' } }, { status: 404 })))
}

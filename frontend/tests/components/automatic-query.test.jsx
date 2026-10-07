import { StrictMode, useState } from 'react'
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AppProviders } from '../../src/app/providers.jsx'
import { useSession } from '../../src/features/auth/SessionProvider.jsx'
import { QueryRefreshProvider } from '../../src/features/history/QueryRefreshProvider.jsx'
import { QueryAction } from '../../src/features/history/QueryAction.jsx'
import { apiClient } from '../../src/api/client.js'
import { OperationController } from '../../src/api/intents.js'
import { envelope, me } from '../fixtures/t2.js'
import { a } from '../fixtures/t4.js'

const path = `/room-bindings/${a}/history-sync`
const range = { start_date: '2026-09-18', end_date: '2026-10-01' }
const id = '0199a10c-0000-7000-8000-000000000090'
const accepted = () => HttpResponse.json(envelope({ operation_id: id }), { status: 202 })
const posts = vi.fn(/** @param {{request: Request}} info */ info => { void info; return accepted() })
const reads = vi.fn(() => HttpResponse.json(envelope({ id, type: 'history_sync', state: 'succeeded' })))
const server = setupServer(
  http.get('/api/v1/auth/session', () => HttpResponse.json(envelope(me))),
  http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))),
  http.post('/api/v1' + path, posts),
  http.get('/api/v1/operations/' + id, reads),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear(); vi.clearAllMocks() })
afterAll(() => server.close())

function Probe() {
  const session = useSession()
  const [page, setPage] = useState(0)
  return <><button onClick={() => { void session.acceptUser({ ...me, credential_status: 'active' }) }}>登录</button>
    <button onClick={() => setPage(value => value + 1)}>切换页面</button>
    <button onClick={() => { void session.refreshUser() }}>刷新资料</button>
    <span>{session.profileStatus}</span>
    {session.status === 'authenticated' && <QueryRefreshProvider>
      <QueryAction key={page} autoRefresh path={path} body={page ? { ...range, start_date: '2026-09-02' } : range} label="同步历史" />
    </QueryRefreshProvider>}</>
}
const mount = () => render(<StrictMode><AppProviders><Probe /></AppProviders></StrictMode>)

it('登录成功自动提交所选日期一次，StrictMode、导航和资料刷新不重复提交', async () => {
  server.use(http.get('/api/v1/auth/session', () => new HttpResponse(null, { status: 401 })))
  mount()
  await screen.findByText('idle')
  expect(posts).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('登录'))
  await waitFor(() => expect(posts).toHaveBeenCalledTimes(1))
  expect(await posts.mock.calls[0][0].request.json()).toEqual(range)
  await waitFor(() => expect(screen.getByRole('button', { name: '同步历史' })).toHaveAttribute('aria-busy', 'false'))
  fireEvent.click(screen.getByText('切换页面'))
  fireEvent.click(screen.getByText('刷新资料'))
  await screen.findByText('ready')
  expect(posts).toHaveBeenCalledTimes(1)
})

it('恢复会话自动同步，浏览器重载后再次同步已完成的请求', async () => {
  const view = mount()
  await waitFor(() => expect(posts).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(new OperationController(me.id).restore()).toHaveLength(0))
  view.unmount()
  mount()
  await waitFor(() => expect(posts).toHaveBeenCalledTimes(2))
})

it('等待学校资料，认证不可用时保留会话且不自动提交，恢复后再执行', async () => {
  server.use(http.get('/api/v1/auth/me', () => new HttpResponse(null, { status: 503 })))
  mount()
  await screen.findByText('unavailable')
  expect(posts).not.toHaveBeenCalled()
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope({ ...me, credential_status: 'requires_reauth' }))))
  fireEvent.click(screen.getByText('刷新资料'))
  await screen.findByText('ready')
  expect(posts).not.toHaveBeenCalled()
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))))
  fireEvent.click(screen.getByText('刷新资料'))
  await waitFor(() => expect(posts).toHaveBeenCalledTimes(1))
})

it('刷新恢复已受理历史只读取原操作，不重复提交', async () => {
  const controller = new OperationController(me.id)
  controller.remember({ ...controller.create(path, range), id })
  mount()
  await waitFor(() => expect(reads).toHaveBeenCalled())
  await waitFor(() => expect(controller.restore()).toHaveLength(0))
  expect(posts).not.toHaveBeenCalled()
})

it('受理未知沿用原键和原日期，429刷新后仍等待且不自动循环重试', async () => {
  const controller = new OperationController(me.id)
  const previousRange = { ...range, start_date: '2026-09-01' }
  const previous = controller.create(path, previousRange)
  const limited = vi.fn(/** @param {{request: Request}} info */ info => {
    void info
    return HttpResponse.json({ error: { code: 'RATE_LIMITED' } }, { status: 429, headers: { 'Retry-After': '60' } })
  })
  server.use(http.post('/api/v1' + path, limited))
  const view = mount()
  await screen.findByText(/请至少等待 60 秒/)
  expect(limited).toHaveBeenCalledTimes(1)
  const request = limited.mock.calls[0][0].request
  expect(request.headers.get('Idempotency-Key')).toBe(previous.key)
  expect(await request.json()).toEqual(previousRange)
  view.unmount()
  mount()
  await screen.findByText(/请至少等待/)
  fireEvent.click(screen.getByText('刷新资料'))
  await act(async () => {})
  expect(limited).toHaveBeenCalledTimes(1)
})

import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from '../fixtures/server.js'
import { useQueryClient } from '@tanstack/react-query'
import App from '../../src/app/App.jsx'
import { AppProviders } from '../../src/app/providers.jsx'
import { useSession } from '../../src/features/auth/SessionProvider.jsx'
import { apiClient } from '../../src/api/client.js'
import { OperationController } from '../../src/api/intents.js'
import { agreement, bindings, captcha, envelope } from '../fixtures/t2.js'

/** @typedef {import('../../src/api/generated').components['schemas']['Me']} Me */
/** @param {string} id @returns {Me} */
const user = (id) => ({ id, school: '合成测试学校', student_id: 'synthetic', credential_status: 'active',
  credential_version: 1, credential_revoke_operation: null, csrf_token: `csrf-${id}`,
  consent: { agreement_version: 'test', accepted_at: '2026-10-01T10:00:00+08:00',
    credential_use_allowed: true, revoked_at: null } })
const first = user('0199a10c-0000-7000-8000-000000000001')
const second = user('0199a10c-0000-7000-8000-000000000002')
const server = setupServer(
  http.get('/api/v1/room-bindings', () => HttpResponse.json(envelope(bindings))),
  http.get('/api/v1/auth/agreement', () => HttpResponse.json(envelope(agreement))),
  http.post('/api/v1/auth/captcha', () => HttpResponse.json(envelope(captcha()))),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear() })
afterAll(() => server.close())

it('初始化完成后保留直达路由，支持导航与服务不可用提示', async () => {
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json({ data: first, meta: { request_id: first.id } })))
  render(<MemoryRouter initialEntries={['/details?start=2026-10-01']}><AppProviders><App /></AppProviders></MemoryRouter>)
  expect(screen.getByText('正在恢复会话…')).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: '电费明细' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('link', { name: '选择与绑定' }))
  expect(screen.getByRole('heading', { name: '选择与绑定' })).toBeInTheDocument()
})

it('应用过期进入登录页，学校异常或不可用不显示登录成功', async () => {
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json({ error: { code: 'APP_SESSION_EXPIRED' },
    meta: { request_id: first.id } }, { status: 401 })))
  const view = render(<MemoryRouter initialEntries={['/monitor']}><AppProviders><App /></AppProviders></MemoryRouter>)
  expect(await screen.findByRole('form', { name: '学校账号登录' })).toBeInTheDocument()
  view.unmount()
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json({ error: { code: 'DEPENDENCY_UNAVAILABLE' },
    meta: { request_id: first.id } }, { status: 503 })))
  render(<MemoryRouter><AppProviders><App /></AppProviders></MemoryRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法连接登录服务')
})

it('切换用户先取消/清空缓存和旧恢复信息，再展示新会话', async () => {
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json({ data: first, meta: { request_id: first.id } })))
  function Probe() {
    const session = useSession()
    const cache = useQueryClient()
    return <><span>{session.user?.id ?? session.status}</span>
      <button onClick={() => {
        cache.setQueryData(['balance', first.id], { private: true })
        new OperationController(first.id).create('/room-bindings/sync')
        void session.acceptUser(second)
      }}>切换</button><span>{cache.getQueryData(['balance', first.id]) ? '旧缓存' : '缓存清空'}</span></>
  }
  render(<AppProviders><Probe /></AppProviders>)
  await screen.findByText(first.id)
  fireEvent.click(screen.getByText('切换'))
  await screen.findByText(second.id)
  expect(screen.getByText('缓存清空')).toBeInTheDocument()
  expect(apiClient.csrfToken).toBe(second.csrf_token)
  await waitFor(() => expect(new OperationController(first.id).restore()).toHaveLength(0))
})

import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AppProviders } from '../../src/app/providers.jsx'
import { useSession } from '../../src/features/auth/SessionProvider.jsx'
import { apiClient } from '../../src/api/client.js'
import { envelope, me } from '../fixtures/t2.js'

const local = { id: me.id, csrf_token: me.csrf_token, consent: me.consent }
const server = setupServer(http.get('/api/v1/auth/session', () => HttpResponse.json(envelope(local))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); vi.restoreAllMocks() })
afterAll(() => server.close())

const second = { ...me, credential_status: /** @type {const} */ ('active'), id: '0199a10c-0000-7000-8000-000000000002', student_id: 'second', csrf_token: 'second-csrf' }
function Probe() {
  const session = useSession()
  return <><span data-testid="status">{session.status}</span><span data-testid="profile-status">{session.profileStatus}</span>
    <span data-testid="user">{session.user?.id}</span><span data-testid="profile">{session.profile?.student_id}</span>
    <button onClick={() => { void session.refreshUser() }}>刷新资料</button>
    <button onClick={() => { void session.initialize() }}>初始化</button>
    <button onClick={() => { void session.acceptUser(second) }}>换账号</button>
  </>
}

it('本地身份先可用，资料503保留登录和CSRF，恢复后加载真实资料', async () => {
  let finish = () => {}
  const pending = new Promise(resolve => { finish = () => resolve(undefined) })
  server.use(http.get('/api/v1/auth/me', async () => { await pending; return new HttpResponse(null, { status: 503 }) }))
  render(<AppProviders><Probe /></AppProviders>)
  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
  expect(screen.getByTestId('profile-status')).toHaveTextContent('loading')
  expect(apiClient.csrfToken).toBe(local.csrf_token)
  await act(async () => { finish() })
  await waitFor(() => expect(screen.getByTestId('profile-status')).toHaveTextContent('unavailable'))
  expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))))
  fireEvent.click(screen.getByText('刷新资料'))
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(me.student_id))
})

it('真实资料401清除本地身份，503不会走旧接口兼容', async () => {
  const profile = vi.fn(() => new HttpResponse(null, { status: 401 }))
  server.use(http.get('/api/v1/auth/me', profile))
  const view = render(<AppProviders><Probe /></AppProviders>)
  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed_out'))
  expect(apiClient.csrfToken).toBeNull()
  view.unmount(); profile.mockClear()
  server.use(http.get('/api/v1/auth/session', () => new HttpResponse(null, { status: 503 })))
  render(<AppProviders><Probe /></AppProviders>)
  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unavailable'))
  expect(profile).not.toHaveBeenCalled()
})

it('仅明确404探测一次旧后端，后续初始化直接使用旧Me', async () => {
  const session = vi.fn(() => new HttpResponse(null, { status: 404 }))
  const profile = vi.fn(() => HttpResponse.json(envelope(me)))
  server.use(http.get('/api/v1/auth/session', session), http.get('/api/v1/auth/me', profile))
  render(<AppProviders><Probe /></AppProviders>)
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent(me.student_id))
  fireEvent.click(screen.getByText('初始化'))
  await waitFor(() => expect(profile).toHaveBeenCalledTimes(2))
  expect(session).toHaveBeenCalledTimes(1)
})

it('换账号后旧资料即使无视取消晚返回也不能覆盖身份、CSRF或资料', async () => {
  let finish = () => {}
  const pending = new Promise(resolve => { finish = () => resolve(undefined) })
  const fetcher = apiClient.fetcher
  vi.spyOn(apiClient, 'fetcher').mockImplementation(async (input, options) => {
    if (String(input).endsWith('/auth/me')) { await pending; return Response.json(envelope(me)) }
    return fetcher(input, options)
  })
  render(<AppProviders><Probe /></AppProviders>)
  await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent(me.id))
  fireEvent.click(screen.getByText('换账号'))
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent('second'))
  await act(async () => { finish() })
  expect(screen.getByTestId('user')).toHaveTextContent(second.id)
  expect(screen.getByTestId('profile')).toHaveTextContent('second')
  expect(apiClient.csrfToken).toBe(second.csrf_token)
})

it('当前代次返回其他账号资料也不能切换本地身份', async () => {
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(second))))
  render(<AppProviders><Probe /></AppProviders>)
  await waitFor(() => expect(screen.getByTestId('profile-status')).toHaveTextContent('unavailable'))
  expect(screen.getByTestId('user')).toHaveTextContent(me.id)
  expect(screen.getByTestId('profile')).toBeEmptyDOMElement()
  expect(apiClient.csrfToken).toBe(local.csrf_token)
})

import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import App from '../../src/app/App.jsx'
import { AppProviders } from '../../src/app/providers.jsx'
import { apiClient } from '../../src/api/client.js'
import { emptyOverview } from '../fixtures/t4.js'
import { monitor } from '../fixtures/t3.js'
import { agreement, bindings, captcha, envelope, me } from '../fixtures/t2.js'
import { AGREEMENT_READ_KEY } from '../../src/features/auth/agreementStorage.js'

const server = setupServer(
  http.get('/api/v1/overview', () => HttpResponse.json(envelope(emptyOverview))),
  http.get('/api/v1/monitor', () => HttpResponse.json(envelope(monitor()))),
  http.get('/api/v1/auth/me', () => HttpResponse.json({ error: { code: 'APP_SESSION_EXPIRED' } }, { status: 401 })),
  http.get('/api/v1/auth/agreement', () => HttpResponse.json(envelope(agreement))),
  http.post('/api/v1/auth/captcha', () => HttpResponse.json(envelope(captcha()))),
  http.get('/api/v1/room-bindings', () => HttpResponse.json(envelope(bindings))),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); vi.restoreAllMocks(); sessionStorage.clear(); localStorage.clear() })
afterAll(() => server.close())

async function completeForm() {
  await screen.findByAltText('学校算式验证码')
  expect(screen.getByLabelText('我同意应用使用协议')).not.toBeChecked()
  expect(screen.queryByLabelText('允许后台使用加密凭据恢复学校认证')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('学校账号'), { target: { value: 'school.account' } })
  fireEvent.change(screen.getByLabelText('学校密码'), { target: { value: ' a password ' } })
  fireEvent.change(screen.getByLabelText('验证码答案'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: '阅读应用协议' }))
  const read = await screen.findByRole('button', { name: '我已阅读' })
  await waitFor(() => expect(read).not.toBeDisabled())
  fireEvent.click(read)
  expect(localStorage.getItem(AGREEMENT_READ_KEY)).toBeNull()
  fireEvent.click(screen.getByLabelText('我同意应用使用协议'))
  expect(screen.getByRole('button', { name: /^登录$/ })).not.toBeDisabled()
}

it('阅读协议后登录统一授权；重复提交只发一次，密码原样提交且成功清理', async () => {
  let count = 0
  let finish = /** @type {(()=>void)|null} */ (null)
  const pending = new Promise(resolve => { finish = () => resolve(null) })
  server.use(http.post('/api/v1/auth/login', async ({ request }) => {
    count += 1
    const body = /** @type {import('../../src/api/generated').components['schemas']['LoginRequest']} */ (await request.json())
    expect(body.password).toBe(' a password ')
    expect(body.student_id).toBe('school.account')
    expect(body.credential_use_allowed).toBe(true)
    await pending
    return HttpResponse.json(envelope({ user: me, bootstrap: { rooms_state: 'loading', requires_binding: null,
      default_binding_id: null, credential_status: 'active' } }))
  }))
  render(<MemoryRouter initialEntries={['/login']}><AppProviders><App /></AppProviders></MemoryRouter>)
  await completeForm()
  const form = screen.getByRole('form', { name: '学校账号登录' })
  fireEvent.submit(form); fireEvent.submit(form)
  await waitFor(() => expect(count).toBe(1))
  if (finish) /** @type {()=>void} */ (finish)()
  await screen.findByRole('heading', { name: '先找到你的寝室' })
  expect(screen.queryByLabelText('学校密码')).not.toBeInTheDocument()
  expect(JSON.stringify(sessionStorage)).not.toContain('password')
  expect(localStorage.getItem(AGREEMENT_READ_KEY)).toBe(`${agreement.version}:${agreement.content_hash}`)
  expect(JSON.stringify(localStorage)).not.toContain('password')
  cleanup()
  render(<MemoryRouter initialEntries={['/login']}><AppProviders><App /></AppProviders></MemoryRouter>)
  await screen.findByAltText('学校算式验证码')
  const consent = screen.getByLabelText('我同意应用使用协议')
  expect(consent).not.toBeChecked()
  expect(consent).toHaveAttribute('aria-disabled', 'false')
  fireEvent.click(consent)
  expect(consent).toBeChecked()
  expect(screen.queryByRole('dialog', { name: '应用使用协议' })).not.toBeInTheDocument()
})

it('学校拒绝后重新取图并清空答案，保留可见错误', async () => {
  let images = 0
  server.use(http.post('/api/v1/auth/captcha', () => HttpResponse.json(envelope(captcha(String(++images))))),
    http.post('/api/v1/auth/login', () => HttpResponse.json({ error: { code: 'SCHOOL_LOGIN_REJECTED',
      message: '学校认证未通过' } }, { status: 401 })))
  render(<MemoryRouter><AppProviders><App /></AppProviders></MemoryRouter>)
  await completeForm()
  fireEvent.click(screen.getByRole('button', { name: /^登录$/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('学校认证未通过')
  await waitFor(() => expect(images).toBe(2))
  expect(screen.getByLabelText('验证码答案')).toHaveValue('')
  expect(localStorage.getItem(AGREEMENT_READ_KEY)).toBeNull()
})

it('未阅读时点击勾选框显示红色说明，完成阅读后说明消失', async () => {
  render(<MemoryRouter><AppProviders><App /></AppProviders></MemoryRouter>)
  await screen.findByAltText('学校算式验证码')
  const consent = screen.getByLabelText('我同意应用使用协议')
  fireEvent.click(consent)
  expect(consent).not.toBeChecked()
  const hint = screen.getByRole('alert')
  expect(hint).toHaveTextContent('请先阅读协议')
  expect(hint).toHaveClass('agreement-read-hint')
  expect(consent).toHaveAttribute('aria-describedby', hint.id)
  fireEvent.click(screen.getByRole('button', { name: '阅读应用协议' }))
  const read = await screen.findByRole('button', { name: '我已阅读' })
  await waitFor(() => expect(read).toBeEnabled())
  fireEvent.click(read)
  expect(screen.queryByText('请先阅读协议')).not.toBeInTheDocument()
  fireEvent.click(consent)
  expect(consent).toBeChecked()
})

it.each([`old:${agreement.content_hash}`, `${agreement.version}:${'b'.repeat(64)}`])(
  '已读记录与版本或正文摘要不一致时要求重新阅读：%s', async stored => {
    localStorage.setItem(AGREEMENT_READ_KEY, stored)
    render(<MemoryRouter><AppProviders><App /></AppProviders></MemoryRouter>)
    await screen.findByAltText('学校算式验证码')
    const consent = screen.getByLabelText('我同意应用使用协议')
    fireEvent.click(consent)
    expect(consent).not.toBeChecked()
    expect(screen.getByRole('alert')).toHaveTextContent('请先阅读协议')
  },
)

it('浏览器禁用持久存储时仍可阅读协议并成功登录', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('blocked', 'SecurityError') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('blocked', 'SecurityError') })
  server.use(http.post('/api/v1/auth/login', () => HttpResponse.json(envelope({ user: me }))))
  render(<MemoryRouter><AppProviders><App /></AppProviders></MemoryRouter>)
  await screen.findByAltText('学校算式验证码')
  fireEvent.change(screen.getByLabelText('学校账号'), { target: { value: 'synthetic' } })
  fireEvent.change(screen.getByLabelText('学校密码'), { target: { value: 'synthetic-only' } })
  fireEvent.change(screen.getByLabelText('验证码答案'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: '阅读应用协议' }))
  const read = await screen.findByRole('button', { name: '我已阅读' })
  await waitFor(() => expect(read).toBeEnabled())
  fireEvent.click(read)
  fireEvent.click(screen.getByLabelText('我同意应用使用协议'))
  fireEvent.click(screen.getByRole('button', { name: /^登录$/ }))
  await screen.findByRole('heading', { name: '先找到你的寝室' })
})

it('寝室查询失败保留应用账户和重试入口，不重提学校密码', async () => {
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))),
    http.get('/api/v1/room-bindings', () => HttpResponse.json(envelope({ ...bindings,
      sync_status: 'failed', last_synced_at: null }))))
  render(<MemoryRouter initialEntries={['/rooms']}><AppProviders><App /></AppProviders></MemoryRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('尚未成功读取学校绑定')
  expect(screen.queryByText('学校已确认当前没有绑定寝室')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '同步学校绑定' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '我的账户' })).toBeInTheDocument()
  expect(screen.queryByRole('form', { name: '学校账号登录' })).not.toBeInTheDocument()
})

import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from '../fixtures/server.js'
import { AppProviders } from '../../src/app/providers.jsx'
import { AccountContent } from '../../src/features/auth/AccountContent.jsx'
import { apiClient } from '../../src/api/client.js'
import { agreement, captcha, envelope, me } from '../fixtures/t2.js'

const server = setupServer(
  http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))),
  http.get('/api/v1/auth/agreement', () => HttpResponse.json(envelope(agreement))),
  http.post('/api/v1/auth/captcha', () => HttpResponse.json(envelope(captcha()))),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear() })
afterAll(() => server.close())

it('账户没有撤回按钮；重新认证阅读协议后仍明确授权后台', async () => {
  let submitted = /** @type {unknown} */ (null)
  server.use(http.post('/api/v1/auth/login', async ({ request }) => {
    submitted = await request.json()
    return HttpResponse.json(envelope({ user: me }))
  }))
  render(<AppProviders><AccountContent onClose={() => {}} /></AppProviders>)
  await screen.findByText('学校账号：synthetic')
  expect(screen.queryByRole('button', { name: '撤回后台授权' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重新学校认证' }))
  await screen.findByAltText('学校算式验证码')
  expect(screen.getByLabelText('学校账号')).toHaveValue('synthetic')
  fireEvent.change(screen.getByLabelText('学校密码'), { target: { value: 'synthetic-only' } })
  fireEvent.change(screen.getByLabelText('验证码答案'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: '阅读应用协议' }))
  const read = await screen.findByRole('button', { name: '我已阅读' })
  await waitFor(() => expect(read).toBeEnabled())
  fireEvent.click(read)
  fireEvent.click(screen.getByLabelText('我同意应用使用协议'))
  fireEvent.click(screen.getByRole('button', { name: '重新认证' }))
  await waitFor(() => expect(submitted).toMatchObject({ credential_use_allowed: true, agreement_accepted: true }))
})

it('升级前正在撤回的操作自动更新终态，不能发起新的撤回', async () => {
  const id = '0199a10c-0000-7000-8000-000000000002'
  let done = false
  const summary = { id, type: 'credential_revoke', state: 'running' }
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope({ ...me,
    credential_status: done ? 'revoked' : 'revoking', credential_revoke_operation: done ? null : summary }))),
  http.get('/api/v1/operations/' + id, () => HttpResponse.json(envelope({ ...summary, state: done ? 'succeeded' : 'running' }))))
  render(<AppProviders><AccountContent onClose={() => {}} /></AppProviders>)
  await screen.findByText('学校认证正在更新…')
  expect(screen.getByRole('button', { name: '重新学校认证' })).toBeDisabled()
  expect(screen.queryByRole('button', { name: '撤回后台授权' })).not.toBeInTheDocument()
  done = true
  expect(screen.queryByRole('button', { name: '查询认证进度' })).not.toBeInTheDocument()
  await screen.findByText('学校认证：已撤回', {}, { timeout: 5000 })
  expect(screen.getByRole('button', { name: '重新学校认证' })).toBeEnabled()
})

import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import App from '../../src/app/App.jsx'
import { AppProviders } from '../../src/app/providers.jsx'
import { apiClient } from '../../src/api/client.js'
import { bindings, envelope, me, requestId } from '../fixtures/t2.js'

const operationId = '0199a10c-0000-7000-8000-000000000002'
const pending = { id: operationId, type: 'credential_revoke', state: 'accepted',
  target_binding_id: null, created_at: '2026-10-01T10:00:00+08:00' }
const server = setupServer(http.get('/api/v1/room-bindings', () => HttpResponse.json(envelope(bindings))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear() })
afterAll(() => server.close())

function mount() {
  render(<MemoryRouter initialEntries={['/rooms']}><AppProviders><App /></AppProviders></MemoryRouter>)
}

it('确认后只提交一次，202 显示处理中；终态后刷新账户且保留弹窗', async () => {
  let phase = 'active'
  let deletes = 0
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope({ ...me,
    credential_status: phase, credential_revoke_operation: phase === 'revoking' ? pending : null }))),
  http.delete('/api/v1/auth/school-credential', async ({ request }) => {
    deletes += 1
    expect(await request.json()).toEqual({ expected_version: 1 })
    phase = 'revoking'
    return HttpResponse.json(envelope({ operation_id: operationId, state: 'accepted',
      poll_url: `/api/v1/operations/${operationId}` }), { status: 202 })
  }), http.get(`/api/v1/operations/${operationId}`, () => HttpResponse.json(envelope({ ...pending,
    state: phase === 'revoked' ? 'succeeded' : 'running' }))))
  mount()
  fireEvent.click(await screen.findByRole('button', { name: '我的账户' }))
  const action = screen.getByRole('button', { name: '撤回后台授权' })
  expect(action).toBeDisabled()
  fireEvent.click(screen.getByLabelText('确认撤回后台授权并删除学校凭据'))
  fireEvent.click(action); fireEvent.click(action)
  await screen.findByText('正在撤回后台授权…')
  expect(deletes).toBe(1)
  expect(screen.queryByText('后台授权已撤回')).not.toBeInTheDocument()
  phase = 'revoked'
  fireEvent.click(screen.getByRole('button', { name: '查询撤回进度' }))
  await screen.findByText('后台授权已撤回')
  expect(screen.getByRole('button', { name: '退出应用' })).toBeInTheDocument()
})

it('刷新后从本人待完成摘要恢复操作，不重复提交撤回', async () => {
  let reads = 0
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope({ ...me, id: requestId,
    credential_status: 'revoking', credential_revoke_operation: pending }))),
  http.get(`/api/v1/operations/${operationId}`, () => { reads += 1; return HttpResponse.json(envelope(pending)) }))
  mount()
  fireEvent.click(await screen.findByRole('button', { name: '我的账户' }))
  await screen.findByText('正在撤回后台授权…')
  await waitFor(() => expect(reads).toBeGreaterThan(0))
  expect(screen.queryByRole('button', { name: '撤回后台授权' })).not.toBeInTheDocument()
})

it('受理响应丢失后从账户摘要恢复，不显示完成或自动重发', async () => {
  let accepted = false
  let deletes = 0
  server.use(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope({ ...me,
    credential_status: accepted ? 'revoking' : 'active',
    credential_revoke_operation: accepted ? pending : null }))),
  http.delete('/api/v1/auth/school-credential', () => {
    accepted = true; deletes += 1
    return HttpResponse.error()
  }), http.get(`/api/v1/operations/${operationId}`, () => HttpResponse.json(envelope(pending))))
  mount()
  fireEvent.click(await screen.findByRole('button', { name: '我的账户' }))
  fireEvent.click(screen.getByLabelText('确认撤回后台授权并删除学校凭据'))
  fireEvent.click(screen.getByRole('button', { name: '撤回后台授权' }))
  await screen.findByText('正在撤回后台授权…')
  expect(screen.queryByText('后台授权已撤回')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '查询撤回进度' }))
  await waitFor(() => expect(deletes).toBe(1))
})

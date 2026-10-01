import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AppProviders } from '../../src/app/providers.jsx'
import { RemoveBindingDialog } from '../../src/features/rooms/RemoveBindingDialog.jsx'
import { RoomOperationStatus } from '../../src/features/rooms/RoomOperationStatus.jsx'
import { apiClient } from '../../src/api/client.js'
import { envelope, me } from '../fixtures/t2.js'

const id = '01970cf0-1234-7000-8000-000000000002'
const binding = { id, room_id: id, building: '枫苑5号', number: '402', display_name: '枫苑5号-402',
  status: /** @type {'active'} */ ('active'), balance: null }
const server = setupServer(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear() })
afterAll(() => server.close())

it('删除目标冻结，明确确认后只发一次DELETE，默认边界可见', async () => {
  let release = /** @type {(()=>void)|null} */ (null)
  const held = new Promise(resolve => { release = () => resolve(null) })
  let count = 0
  server.use(http.delete(`/api/v1/room-bindings/${id}`, async ({ request }) => {
    count += 1
    expect(request.headers.get('Idempotency-Key')).toBeTruthy()
    await held
    return HttpResponse.json(envelope({ operation_id: id, state: 'accepted', poll_url: `/api/v1/operations/${id}` }), { status: 202 })
  }))
  const accepted = vi.fn()
  render(<AppProviders><RemoveBindingDialog binding={binding} isDefault onClose={vi.fn()} onAccepted={accepted} /></AppProviders>)
  await waitFor(() => expect(apiClient.csrfToken).toBe(me.csrf_token))
  const button = screen.getByRole('button', { name: '确认删除绑定' })
  expect(button).toBeDisabled()
  expect(screen.getByText(/监控先暂停旧目标/)).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('我确认解除该寝室的学校绑定'))
  fireEvent.click(button); fireEvent.click(button)
  await waitFor(() => expect(count).toBe(1))
  if (release) /** @type {()=>void} */ (release)()
  await waitFor(() => expect(accepted).toHaveBeenCalledWith(id))
})

it('未知删除只查询进度，确认解除与清空默认分开显示', async () => {
  let done = false
  server.use(http.get(`/api/v1/operations/${id}`, () => HttpResponse.json(envelope({ id, type: 'unbind_room',
    state: done ? 'succeeded' : 'unknown', binding_status: done ? 'removed' : 'unknown',
    default_status: done ? 'confirmed' : 'switching', error_code: null }))))
  render(<AppProviders><RoomOperationStatus id={id} /></AppProviders>)
  await screen.findByText('学校解绑：结果尚未确认')
  expect(screen.getByText(/请勿重复提交/)).toBeInTheDocument()
  done = true
  fireEvent.click(screen.getByRole('button', { name: '查询最新进度' }))
  await screen.findByText('解绑状态：学校已解除绑定')
  expect(screen.getByText('默认状态：已清空默认，监控等待新目标')).toBeInTheDocument()
})

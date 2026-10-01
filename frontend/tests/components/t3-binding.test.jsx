import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AppProviders } from '../../src/app/providers.jsx'
import { BindingDialog } from '../../src/features/rooms/BindingDialog.jsx'
import { RoomOperationStatus } from '../../src/features/rooms/RoomOperationStatus.jsx'
import { apiClient } from '../../src/api/client.js'
import { envelope, me } from '../fixtures/t2.js'

const id = '01970cf0-1234-7000-8000-000000000002'
const server = setupServer(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear() })
afterAll(() => server.close())

it('慢响应和重复点击只受理一次，目标在弹窗中冻结', async () => {
  let release = /** @type {(()=>void)|null} */ (null)
  const held = new Promise(resolve => { release = () => resolve(null) })
  const writes = /** @type {unknown[]} */ ([])
  server.use(http.post('/api/v1/room-bindings', async ({ request }) => {
    writes.push(await request.json())
    await held
    return HttpResponse.json(envelope({ operation_id: id, state: 'accepted', poll_url: `/api/v1/operations/${id}` }), { status: 202 })
  }))
  const accepted = vi.fn()
  render(<AppProviders><BindingDialog candidate={{ candidate_id: 'frozen-candidate', room_id: 'r402',
    building: '枫苑5号', number: '402', display_name: '枫苑5号-402', already_bound: false,
    expires_at: new Date(Date.now() + 300_000).toISOString() }} onClose={vi.fn()} onAccepted={accepted} /></AppProviders>)
  await waitFor(() => expect(apiClient.csrfToken).toBe(me.csrf_token))
  const button = screen.getByRole('button', { name: '确认绑定' })
  fireEvent.click(button); fireEvent.click(button)
  await waitFor(() => expect(writes).toEqual([{ candidate_id: 'frozen-candidate' }]))
  if (release) /** @type {()=>void} */ (release)()
  await waitFor(() => expect(accepted).toHaveBeenCalledWith(id))
  expect(writes).toHaveLength(1)
})

it('未知绑定只查询原操作，绑定确认而默认失败分别显示', async () => {
  let state = 'unknown'
  server.use(http.get(`/api/v1/operations/${id}`, () => HttpResponse.json(envelope({ id, type: 'bind_room',
    state, binding_status: state === 'unknown' ? 'unknown' : 'confirmed',
    default_status: state === 'unknown' ? 'pending' : 'failed', error_code: null }))))
  render(<AppProviders><RoomOperationStatus id={id} /></AppProviders>)
  await screen.findByText('学校绑定：结果尚未确认')
  expect(screen.getByText(/后台只回查学校结果/)).toBeInTheDocument()
  state = 'succeeded'
  fireEvent.click(screen.getByRole('button', { name: '查询最新进度' }))
  await screen.findByText('绑定状态：学校已确认')
  expect(screen.getByText('默认状态：默认设置失败，已绑定关系保留')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '确认绑定' })).not.toBeInTheDocument()
})

import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from '../fixtures/server.js'
import { AppProviders } from '../../src/app/providers.jsx'
import { BindingDialog } from '../../src/features/rooms/BindingDialog.jsx'
import { RoomOperationStatus } from '../../src/features/rooms/RoomOperationStatus.jsx'
import { BindingRecovery } from '../../src/features/rooms/BindingRecovery.jsx'
import { apiClient } from '../../src/api/client.js'
import { OperationController } from '../../src/api/intents.js'
import { envelope, me } from '../fixtures/t2.js'

const id = '01970cf0-1234-7000-8000-000000000002'
const server = setupServer(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear() })
afterAll(() => server.close())

it('功能关闭的503是明确未受理，弹窗与刷新恢复不会留下待确认请求', async () => {
  server.use(http.post('/api/v1/room-bindings', () => HttpResponse.json({
    error: { code: 'FEATURE_DISABLED', message: '新增学校绑定尚未开放' }, meta: envelope(null).meta,
  }, { status: 503 })))
  render(<AppProviders><BindingDialog candidate={{ candidate_id: 'closed-candidate', room_id: 'r402',
    building: '合成楼', number: '402', display_name: '合成楼-402', already_bound: false,
    expires_at: new Date(Date.now() + 300_000).toISOString() }} onClose={vi.fn()} onAccepted={vi.fn()} />
    <BindingRecovery onAccepted={vi.fn()} /></AppProviders>)
  await waitFor(() => expect(apiClient.csrfToken).toBe(me.csrf_token))
  fireEvent.click(screen.getByRole('button', { name: '确认绑定' }))
  await screen.findByText('新增学校绑定尚未开放')
  expect(screen.getByRole('button', { name: '确认绑定' })).toBeEnabled()
  expect(screen.queryByText('有一笔学校绑定受理尚未确认')).not.toBeInTheDocument()
  expect(new OperationController(me.id).restore()).toEqual([])
})

it('停止一条历史本地重试不发送学校请求，其他未知请求继续保留', async () => {
  const controller = new OperationController(me.id)
  controller.create('/room-bindings', { candidate_id: 'old-candidate-one' })
  const other = controller.create('/room-bindings', { candidate_id: 'old-candidate-two' })
  const writes = vi.fn()
  server.use(http.post('/api/v1/room-bindings', () => { writes(); return HttpResponse.error() }))
  render(<AppProviders><BindingRecovery onAccepted={vi.fn()} /></AppProviders>)
  await screen.findAllByText('有一笔学校绑定受理尚未确认')
  fireEvent.click(screen.getAllByRole('button', { name: '停止本地重试' })[0])
  await screen.findByText('已停止本地重试；学校请求仍可能已受理，请同步学校绑定核对。')
  expect(writes).not.toHaveBeenCalled()
  expect(new OperationController(me.id).restore().map(value => value.key)).toEqual([other.key])
})

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
  expect(screen.queryByRole('button', { name: '查询最新进度' })).not.toBeInTheDocument()
  await screen.findByText('绑定状态：学校已确认', {}, { timeout: 4000 })
  expect(screen.getByText('默认状态：默认设置失败，已绑定关系保留')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '确认绑定' })).not.toBeInTheDocument()
})

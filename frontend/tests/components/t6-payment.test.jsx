import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from '../fixtures/server.js'
import { AppProviders } from '../../src/app/providers.jsx'
import { apiClient } from '../../src/api/client.js'
import { PaymentDialog } from '../../src/features/payments/PaymentDialog.jsx'
import { PaymentQr } from '../../src/features/payments/PaymentQr.jsx'
import { envelope, me } from '../fixtures/t2.js'
import { bindingId, capability, order, orderId } from '../fixtures/t6.js'

const server = setupServer(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))),
  http.get('/api/v1/payments/capabilities', () => HttpResponse.json(envelope(capability))),
  http.get(`/api/v1/payment-orders/${orderId}`, () => HttpResponse.json(envelope(order))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset(); sessionStorage.clear(); vi.clearAllMocks() })
afterAll(() => server.close())

it('能力关闭或分币不满足整数步长时禁止建单', async () => {
  const writes = vi.fn()
  server.use(http.post('/api/v1/payment-orders', () => { writes(); return HttpResponse.error() }),
    http.get('/api/v1/payments/capabilities', () => HttpResponse.json(envelope({ ...capability,
      enabled: false, unavailable_reason: '支付尚未完成真实验收' }))))
  const result = render(<AppProviders><PaymentDialog bindingId={bindingId} displayName="合成寝室" onClose={vi.fn()} /></AppProviders>)
  await screen.findByText('支付尚未完成真实验收')
  expect(screen.queryByRole('button', { name: '确认创建充值订单' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('充值金额（元）')).not.toBeInTheDocument()
  result.unmount()
  server.use(http.get('/api/v1/payments/capabilities', () => HttpResponse.json(envelope(capability))))
  render(<AppProviders><PaymentDialog bindingId={bindingId} displayName="合成寝室" onClose={vi.fn()} /></AppProviders>)
  await screen.findByText(/每次递增/)
  fireEvent.change(screen.getByLabelText('充值金额（元）'), { target: { value: '1.01' } })
  expect(screen.getByRole('button', { name: '确认创建充值订单' })).toBeDisabled()
  expect(writes).not.toHaveBeenCalled()
})

it('受理响应丢失后关闭重开使用原金额和原键，重复点击不创建第二个逻辑订单', async () => {
  const keys = /** @type {(string|null)[]} */ ([])
  const bodies = /** @type {unknown[]} */ ([])
  server.use(http.post('/api/v1/payment-orders', async ({ request }) => {
    keys.push(request.headers.get('Idempotency-Key')); bodies.push(await request.json())
    return keys.length === 1 ? HttpResponse.error() : HttpResponse.json(envelope({ order_id: orderId,
      state: 'created', poll_url: `/api/v1/payment-orders/${orderId}` }), { status: 202 })
  }))
  const first = render(<AppProviders><PaymentDialog bindingId={bindingId} displayName="合成寝室" onClose={vi.fn()} /></AppProviders>)
  await screen.findByText(/每次递增/)
  fireEvent.change(screen.getByLabelText('充值金额（元）'), { target: { value: '30' } })
  const submit = screen.getByRole('button', { name: '确认创建充值订单' })
  fireEvent.click(submit); fireEvent.click(submit)
  await screen.findByText(/原订单受理结果待确认/)
  await waitFor(() => expect(screen.getByRole('button', { name: '重试原订单请求' })).toBeEnabled())
  first.unmount()
  render(<AppProviders><PaymentDialog bindingId={bindingId} displayName="合成寝室" onClose={vi.fn()} /></AppProviders>)
  await screen.findByText(/原订单受理结果待确认/)
  expect(screen.getByLabelText('充值金额（元）')).toHaveValue('30.00')
  expect(screen.getByLabelText('充值金额（元）')).toBeDisabled()
  await waitFor(() => expect(screen.getByRole('button', { name: '重试原订单请求' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '重试原订单请求' }))
  await screen.findByText('支付状态尚未确认')
  expect(keys).toHaveLength(2); expect(keys[0]).toBe(keys[1])
  expect(bodies).toEqual([{ binding_id: bindingId, amount: '30.00' }, { binding_id: bindingId, amount: '30.00' }])
  expect(screen.queryByText('学校已确认支付')).not.toBeInTheDocument()
})

it('服务器未解决订单在能力关闭和浏览器记录丢失后仍可恢复', async () => {
  server.use(http.get('/api/v1/payments/capabilities', () => HttpResponse.json(envelope({ ...capability,
    enabled: false, unavailable_reason: '支付暂未开放', unresolved_order: order }))))
  render(<AppProviders><PaymentDialog bindingId={bindingId} displayName="合成寝室" onClose={vi.fn()} /></AppProviders>)
  await screen.findByText('支付状态尚未确认')
  expect(screen.queryByRole('button', { name: '确认创建充值订单' })).not.toBeInTheDocument()
  expect(screen.getByText(/关闭窗口不会取消订单/)).toBeInTheDocument()
})

it('二维码202不创建图片URL；图片更新和关闭释放旧URL，200 HTML被拒绝', async () => {
  URL.createObjectURL = vi.fn(() => 'blob:synthetic-qr')
  URL.revokeObjectURL = vi.fn()
  let ready = false
  server.use(http.get(`/api/v1/payment-orders/${orderId}/qr`, () => ready
    ? new HttpResponse(new Uint8Array([137, 80, 78, 71]), { headers: { 'Content-Type': 'image/png' } })
    : HttpResponse.json(envelope({ order_id: orderId, qr_status: 'generating', poll_url: '', retry_after_seconds: 5 }), { status: 202 })))
  const result = render(<AppProviders><PaymentQr order={{ ...order, qr_status: 'generating' }} onRefresh={vi.fn()} /></AppProviders>)
  await screen.findByText('正在取得原订单二维码…')
  expect(URL.createObjectURL).not.toHaveBeenCalled()
  ready = true
  result.rerender(<AppProviders><PaymentQr order={{ ...order, qr_status: 'ready' }} onRefresh={vi.fn()} /></AppProviders>)
  await screen.findByAltText('此充值订单的微信支付二维码')
  result.unmount()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-qr')
  server.use(http.get(`/api/v1/payment-orders/${orderId}/qr`, () => new HttpResponse('<html>error</html>', { headers: { 'Content-Type': 'text/html' } })))
  render(<AppProviders><PaymentQr order={{ ...order, qr_status: 'ready' }} onRefresh={vi.fn()} /></AppProviders>)
  await screen.findByText('二维码接口未返回有效图片')
})


it('取消原订单清理二维码与原引用，重新选择默认1元；重复点击只提交一次', async () => {
  let cancelled = false
  const calls = vi.fn()
  const original = { ...order, state: 'submit_unknown', qr_status: 'not_requested' }
  server.use(
    http.get('/api/v1/payments/capabilities', () => HttpResponse.json(envelope({ ...capability,
      unresolved_order: cancelled ? null : original }))),
    http.get(`/api/v1/payment-orders/${orderId}`, () => HttpResponse.json(envelope(cancelled ? {
      ...original, version: 2, cancelled_at: '2026-10-02T03:00:00+08:00' } : original))),
    http.post(`/api/v1/payment-orders/${orderId}/cancel`, async ({ request }) => {
      calls(await request.json()); cancelled = true
      await new Promise(resolve => setTimeout(resolve, 20))
      return HttpResponse.json(envelope({ ...original, version: 2,
        cancelled_at: '2026-10-02T03:00:00+08:00' }))
    }))
  render(<AppProviders><PaymentDialog bindingId={bindingId} displayName="合成寝室" onClose={vi.fn()} /></AppProviders>)
  await screen.findByText('建单结果尚未确认')
  fireEvent.click(screen.getByRole('button', { name: '停止处理此订单' }))
  expect(screen.getByText(/停止处理不会退款/)).toBeVisible()
  const button = screen.getByRole('button', { name: '确认停止处理' })
  fireEvent.click(button); fireEvent.click(button)
  await screen.findByText('本系统已停止处理')
  expect(calls).toHaveBeenCalledExactlyOnceWith({ expected_version: 1 })
  expect(screen.queryByAltText('此充值订单的微信支付二维码')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重新选择充值金额' }))
  await waitFor(() => expect(screen.getByLabelText('充值金额（元）')).toHaveValue('1'))
  expect(screen.getByRole('button', { name: '确认创建充值订单' })).toBeEnabled()
})

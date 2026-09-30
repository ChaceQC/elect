import { afterAll, afterEach, beforeAll, expect, test } from 'vitest'
import { setupServer } from 'msw/node'
import { handlersFor } from '../../src/mocks/handlers.js'

const server = setupServer()
/** @param {string} path */
const api = path => new URL(`/api/v1${path}`, window.location.href)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

test('学校读取失败保留过期余额，不以空列表代替失败', async () => {
  server.use(...handlersFor('school_failed'))
  const failed = await fetch(api('/room-candidates'))
  expect(failed.status).toBe(503)
  expect((await failed.json()).error.code).toBe('SCHOOL_UNAVAILABLE')
  const bindings = await (await fetch(api('/room-bindings'))).json()
  expect(bindings.data.sync_status).toBe('stale')
  expect(bindings.data.items[0].balance.amount).toBe('25.50')
  expect(bindings.data.items[0].balance.stale).toBe(true)
})

test('未知订单恢复原订单，二维码有效期和付款结果保持未知', async () => {
  server.use(...handlersFor('unknown_order'))
  const capabilities = await (await fetch(api('/payments/capabilities'))).json()
  const ref = capabilities.data.unresolved_order
  const order = await (await fetch(api(`/payment-orders/${ref.order_id}`))).json()
  expect(capabilities.data.enabled).toBe(false)
  expect(order.data.order_id).toBe(ref.order_id)
  expect(order.data.state).toBe('submit_unknown')
  expect(order.data.paid_confirmed).toBe(false)
  expect(order.data.qr_expires_at).toBeNull()
})

test('部分历史区分明确零消费和未知日', async () => {
  server.use(...handlersFor('partial_history'))
  const result = await (await fetch(api('/room-bindings/fixture/consumption'))).json()
  expect(result.data.buckets.map(/** @param {{amount:string|null}} bucket */ bucket => bucket.amount))
    .toEqual(['0.00', null])
  expect(result.data.coverage).toBe('partial')
})

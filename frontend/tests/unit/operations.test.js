import { beforeEach, expect, it, vi } from 'vitest'
import { ApiClient, ApiError } from '../../src/api/client.js'
import { OperationController, clearRecovery } from '../../src/api/intents.js'
import { isTerminal, pollInterval } from '../../src/api/operations.js'
import { VersionedDraft } from '../../src/lib/versionedDraft.js'
import { resourceKey } from '../../src/app/queryKeys.js'
import { moneyLabel, validateAmount } from '../../src/lib/money.js'
import { shanghaiDate, validDateRange } from '../../src/lib/dates.js'

const user = '0199a10c-0000-7000-8000-000000000001'
const order = '0199a10c-0000-7000-8000-000000000002'
beforeEach(() => sessionStorage.clear())

it('网络失败保留原幂等键/原请求，202 只记录受理 ID，刷新不重提交', async () => {
  const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('network'))
    .mockResolvedValue(Response.json({ data: { order_id: order, state: 'created', poll_url: 'https://foreign.example/' },
      meta: { request_id: user } }, { status: 202 }))
  const controller = new OperationController(user, new ApiClient(fetcher))
  const body = { binding_id: order, amount: '20.00' }
  const intent = controller.create('/payment-orders', body, 'order')
  body.amount = '50.00'
  await expect(controller.submit(intent)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const restored = new OperationController(user, controller.client).restore()[0]
  const accepted = await controller.submit(restored)
  expect(accepted.id).toBe(order)
  expect(fetcher.mock.calls.map(([, options]) => options.headers.get('Idempotency-Key'))).toEqual([intent.key, intent.key])
  expect(JSON.parse(fetcher.mock.calls[1][1].body).amount).toBe('20.00')
  await controller.submit(accepted)
  expect(fetcher).toHaveBeenCalledTimes(2)
  expect(new OperationController(order).restore()).toHaveLength(0)
  clearRecovery(user)
  expect(new OperationController(user).restore()).toHaveLength(0)
})

it('恢复信息拒绝凭据/嵌套字段，服务端摘要只用于查询既有对象', async () => {
  const controller = new OperationController(user)
  expect(() => controller.create('/payment-orders', { token: 'private' })).toThrow('敏感')
  expect(() => controller.create('/auth/login', {})).toThrow('幂等')
  const recovered = controller.recoverSummaries('order', [order, order])
  expect(recovered).toHaveLength(1)
  expect(await controller.submit(recovered[0])).toEqual(recovered[0])
  expect(sessionStorage.getItem(`elect.intent.${user}.${recovered[0].key}`)).not.toContain('csrf')
})

it('隐藏暂停轮询，unknown 保持未解决，两分钟后手动查，二维码不当成付款', () => {
  expect(pollInterval('operation', 'unknown', 10_000, true)).toBe(2000)
  expect(pollInterval('run', 'running', 30_000, true)).toBe(5000)
  expect(pollInterval('order', 'awaiting_payment', 90_000, true)).toBe(10_000)
  expect(pollInterval('order', 'submit_unknown', 120_000, true)).toBe(false)
  expect(pollInterval('run', 'running', 0, false)).toBe(false)
  expect(isTerminal('order', 'awaiting_payment')).toBe(false)
  expect(isTerminal('order', 'paid_confirmed')).toBe(true)
})

it('版本冲突和响应丢失先读取当前状态，保留草稿并阻断盲重写', async () => {
  const draft = new VersionedDraft({ interval: 75 }, 1)
  const write = vi.fn().mockRejectedValueOnce(new ApiError('VERSION_CONFLICT', 'conflict', 409))
    .mockResolvedValue({ value: { interval: 75 }, version: 3 })
  const current = vi.fn().mockResolvedValue({ value: { interval: 120 }, version: 2 })
  expect((await draft.save(write, current)).status).toBe('conflict')
  expect(draft.draft.interval).toBe(75)
  await expect(draft.save(write, current)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  expect(write).toHaveBeenCalledOnce()
  draft.acknowledgeCurrent(2)
  expect((await draft.save(write, current)).status).toBe('saved')
  expect(write.mock.calls[1][1]).toBe(2)
  const lost = new VersionedDraft({ interval: 60 }, 1)
  expect((await lost.save(async () => { throw new ApiError('NETWORK_ERROR', 'lost', 0) }, current)).status).toBe('reconcile')
  expect(lost.reviewRequired).toBe(true)
})

it('用户/日期/快照隔离缓存，金额用十进制，日期按上海', () => {
  expect(resourceKey('samples', user, { snapshot: 'batch-1' })).not.toEqual(resourceKey('samples', order, { snapshot: 'batch-1' }))
  expect(resourceKey('samples', user, { snapshot: 'batch-1' })).not.toEqual(resourceKey('samples', user, { snapshot: 'batch-2' }))
  expect(moneyLabel(null)).toBe('—')
  expect(validateAmount('20.00', { minimum: '1.00', maximum: '500.00', step: '1.00' })).toBe(true)
  expect(validateAmount('20.01', { minimum: '1.00', maximum: '500.00', step: '1.00' })).toBe(false)
  expect(shanghaiDate(new Date('2026-09-30T17:00:00Z'))).toBe('2026-10-01')
  expect(validDateRange('2026-02-30', '2026-03-01')).toBe(false)
  expect(validDateRange('2026-01-01', '2027-01-01')).toBe(true)
  expect(validDateRange('2026-01-01', '2027-01-02')).toBe(false)
})

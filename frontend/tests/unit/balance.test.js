import { expect, it } from 'vitest'
import { isBalanceStale } from '../../src/lib/balance.js'

it('余额新鲜度使用采集时间，超过五分钟变过期；未知或服务端过期不变新鲜', () => {
  const balance = { stale: false, fetched_at: '2026-10-04T10:00:00+08:00' }
  const fetched = Date.parse(balance.fetched_at)
  expect(isBalanceStale(balance, fetched + 300_000)).toBe(false)
  expect(isBalanceStale(balance, fetched + 300_001)).toBe(true)
  expect(isBalanceStale({ ...balance, stale: true }, fetched)).toBe(true)
  expect(isBalanceStale({ ...balance, fetched_at: null }, fetched)).toBe(true)
  expect(isBalanceStale(null, fetched)).toBe(true)
})

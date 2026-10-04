import { expect, test } from '@playwright/test'
import { visualFixture } from '../fixtures/visual.js'
import { envelope } from '../fixtures/t2.js'
import { capability, order, orderId } from '../fixtures/t6.js'

test('支付长等待仍每两秒更新、隐藏暂停、恢复确认并等待余额，终态停止', async ({ page }) => {
  await page.clock.install()
  await page.addInitScript(() => {
    window.paymentTestVisibility = 'visible'
    Object.defineProperty(document, 'visibilityState', { get: () => window.paymentTestVisibility })
  })
  await visualFixture(page)
  let reads = 0
  let current = order
  await page.route('**/api/v1/payments/capabilities?*', route => route.fulfill({ json: envelope({ ...capability, unresolved_order: order }) }))
  await page.route('**/api/v1/payment-orders/' + orderId, route => {
    reads += 1
    return route.fulfill({ json: envelope(current) })
  })
  await page.goto('/rooms')
  await page.getByRole('button', { name: '查看原充值订单' }).click()
  await expect(page.getByText('支付状态尚未确认')).toBeVisible()
  await page.clock.fastForward(601_000)
  await expect(page.getByRole('button', { name: '恢复自动更新' })).toHaveCount(0)
  await page.clock.fastForward(2100)
  await expect.poll(() => reads).toBeGreaterThan(1)
  const previousReads = reads
  await page.clock.fastForward(2100)
  await expect.poll(() => reads).toBeGreaterThan(previousReads)
  await page.evaluate(() => {
    window.paymentTestVisibility = 'hidden'
    document.dispatchEvent(new Event('visibilitychange'))
  })
  const hiddenReads = reads
  await page.clock.fastForward(30_000)
  expect(reads).toBe(hiddenReads)
  current = { ...order, state: 'paid_confirmed', paid_confirmed: true, balance_refresh_state: 'pending' }
  await page.evaluate(() => {
    window.paymentTestVisibility = 'visible'
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(page.getByText('学校已确认支付')).toBeVisible()
  await expect(page.getByText('支付已确认，正在重新查询学校余额。')).toBeVisible()
  current = { ...current, balance_refresh_state: 'succeeded' }
  await page.clock.fastForward(2100)
  await expect(page.getByText('学校余额已重新查询，到账以查询结果为准。')).toBeVisible()
  const finishedReads = reads
  await page.clock.fastForward(60_000)
  expect(reads).toBe(finishedReads)
})

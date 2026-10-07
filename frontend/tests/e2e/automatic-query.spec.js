import { expect, test } from '@playwright/test'
import { visualFixture } from '../fixtures/visual.js'
import { envelope } from '../fixtures/t2.js'
import { a, balance, consumption } from '../fixtures/t4.js'

for (const width of [1440, 375]) {
  test(`${width}px：总览与明细重载自动刷新余额和趋势，导航及粒度切换不重复提交`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const unexpected = await visualFixture(page)
    const requests = []
    let balanceVersion = 0, historyVersion = 0
    const ids = new Map()
    await page.route('**/api/v1/room-bindings/*/balance-refresh', route => {
      const id = `0199a10c-0000-7000-8000-${String(200 + ++balanceVersion).padStart(12, '0')}`
      requests.push({ type: 'balance', key: route.request().headers()['idempotency-key'] })
      ids.set(id, 'balance_refresh')
      return route.fulfill({ status: 202, json: envelope({ operation_id: id }) })
    })
    await page.route('**/api/v1/room-bindings/*/history-sync', route => {
      const id = `0199a10c-0000-7000-8000-${String(300 + ++historyVersion).padStart(12, '0')}`
      requests.push({ type: 'history', key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON() })
      ids.set(id, 'history_sync')
      return route.fulfill({ status: 202, json: envelope({ operation_id: id }) })
    })
    await page.route('**/api/v1/operations/*', route => {
      const id = new URL(route.request().url()).pathname.split('/').at(-1)
      return route.fulfill({ json: envelope({ id, type: ids.get(id), state: 'succeeded' }) })
    })
    await page.route('**/api/v1/room-bindings/*/balance', route =>
      route.fulfill({ json: envelope(balance(balanceVersion ? `8${balanceVersion}.00` : '86.42')) }))
    await page.route('**/api/v1/overview', async route => {
      // 从固定夹具构造总览，只把任务完成后的消费金额变化用于断言。
      const start = '2026-09-17', end = '2026-09-30'
      const history = consumption(start, end)
      history.summary.amount = historyVersion ? '23.45' : '1.50'
      await route.fulfill({ json: envelope({ viewing_binding_id: a, profile: null, balance: null, monitor: null,
        summary: { yesterday_amount: null, last_14_days_amount: history.summary.amount, known_days: 2, expected_days: 14, complete: false },
        daily_consumption: history, component_status: { profile: 'unavailable', balance: 'ready', history: 'ready', monitor: 'unavailable' } }) })
    })
    await page.goto('/overview')
    await expect(page.locator('.balance-amount')).toHaveText('¥81.00')
    await expect(page.locator('.stat').filter({ hasText: '近 14 天消费' })).toContainText('23.45')
    await expect(page.getByRole('button', { name: '同步最近14天学校历史' })).toHaveAttribute('aria-busy', 'false')
    expect(requests).toHaveLength(2)
    expect(requests.find(item => item.type === 'history').body).toEqual({ start_date: '2026-09-17', end_date: '2026-09-30' })
    await page.getByRole('link', { name: '电费明细', exact: true }).click()
    await page.getByRole('button', { name: '周', exact: true }).click()
    await expect(page.locator('.consumption-chart canvas')).toBeVisible()
    expect(requests).toHaveLength(2)
    await page.reload()
    await expect(page.locator('.balance-amount')).toHaveText('¥82.00')
    await expect(page.getByRole('button', { name: '同步所选范围的学校历史' })).toHaveAttribute('aria-busy', 'false')
    await expect.poll(() => requests.length).toBe(4)
    expect(new Set(requests.map(item => item.key)).size).toBe(4)
    expect(requests.filter(item => item.type === 'history')[1].body).toEqual({ start_date: '2026-09-02', end_date: '2026-10-01' })
    expect(unexpected).toEqual([])
  })
}

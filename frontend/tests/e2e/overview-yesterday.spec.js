import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { envelope, me } from '../fixtures/t2.js'
import { monitor } from '../fixtures/t3.js'
import { a, balance, consumption, rooms } from '../fixtures/t4.js'

for (const width of [1440, 375]) {
  test(`${width}px：昨日金额与曲线一致，估算、零值和缺失分别展示`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    /** @type {{ amount: string | null, estimated: string | null }} */
    let current = { amount: '4.41', estimated: '4.41' }
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(rooms) })
      if (path === '/api/v1/monitor') return route.fulfill({ json: envelope(monitor()) })
      if (path.endsWith('/balance')) return route.fulfill({ json: envelope(balance('15.81')) })
      if (path === '/api/v1/overview') {
        const history = consumption('2026-09-25', '2026-10-08')
        history.buckets = history.buckets.map(bucket => ({ ...bucket,
          amount: bucket.start_date === '2026-10-04' ? null : bucket.start_date === '2026-10-07' ? current.amount : '0.00',
          known_days: bucket.start_date === '2026-10-04' || bucket.start_date === '2026-10-07' && current.amount == null ? 0 : 1,
          complete: bucket.start_date !== '2026-10-04' && (bucket.start_date !== '2026-10-07' || current.amount != null),
          estimated_amount: bucket.start_date === '2026-10-07' ? current.estimated : bucket.start_date === '2026-10-06' ? '0.00' : null,
          estimated_days: bucket.start_date === '2026-10-06' || bucket.start_date === '2026-10-07' && current.estimated != null ? 1 : 0 }))
        history.summary = { ...history.summary, amount: current.amount ?? '0.00',
          known_days: current.amount == null ? 12 : 13, complete: false,
          estimated_amount: current.estimated ?? '0.00', estimated_days: current.estimated == null ? 1 : 2 }
        return route.fulfill({ json: envelope({ viewing_binding_id: a,
          profile: { student_id: 'synthetic', default_binding: rooms.items[0], alert_email: null },
          balance: balance('15.81'), daily_consumption: history, monitor: null,
          summary: { yesterday_amount: current.amount, yesterday_estimated_amount: current.estimated,
            last_14_days_amount: history.summary.amount, known_days: history.summary.known_days, expected_days: 14, complete: false },
          component_status: { profile: 'ready', balance: 'ready', history: 'partial', monitor: 'unavailable' } }) })
      }
      return route.fulfill({ status: 404 })
    })
    const card = page.locator('.stat-grid .stat').first()
    await page.goto('/overview')
    await expect(card.locator('.stat-value')).toHaveText('4.41元')
    await expect(card).toContainText('含余额变化估算')
    await expect(card).not.toContainText('尚未取得')
    await expect(page.locator('.stat-grid .stat').nth(1)).toContainText('已知13/14天')
    await expect(page.getByRole('img', { name: /含余额变化估算/ })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (process.env.ELECT_T4_SCREENSHOT_DIR) {
      await mkdir(process.env.ELECT_T4_SCREENSHOT_DIR, { recursive: true })
      await page.screenshot({ path: `${process.env.ELECT_T4_SCREENSHOT_DIR}/overview-yesterday-${width}.png`, fullPage: true })
    }
    for (const item of [
      { amount: '3.90', estimated: null },
      { amount: '0.00', estimated: '0.00' },
      { amount: '0.00', estimated: null },
      { amount: null, estimated: null },
    ]) {
      current = item
      await page.reload()
      await expect(card.locator('.stat-value')).toHaveText(`${item.amount ?? '—'}元`)
      if (item.estimated != null) await expect(card).toContainText('含余额变化估算')
      else await expect(card).not.toContainText('含余额变化估算')
      if (item.amount == null) await expect(card).toContainText('昨日消费尚未取得')
      else await expect(card).not.toContainText('尚未取得')
    }
  })
}

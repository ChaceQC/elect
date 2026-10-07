import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { envelope, me } from '../fixtures/t2.js'
import { monitor } from '../fixtures/t3.js'
import { a, balance, consumption, rooms } from '../fixtures/t4.js'

for (const width of [1440, 375]) {
  test(`${width}px：总览和明细显示监控估算，学校数据替换估算，刷新采集同步趋势`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let synced = false
    let consumptionReads = 0
    let unavailable = false
    /** @param {string} start @param {string} end */
    function merged(start, end) {
      const value = consumption(start, end)
      value.buckets = value.buckets.map((bucket, i) => ({ ...bucket,
        amount: i === 0 ? synced ? '2.50' : '1.30' : null,
        known_days: i === 0 ? 1 : 0, estimated_amount: i === 0 && !synced ? '1.30' : null,
        estimated_days: i === 0 && !synced ? 1 : 0 }))
      value.summary = { ...value.summary, amount: synced ? '2.50' : '1.30', known_days: 1,
        estimated_amount: synced ? null : '1.30', estimated_days: synced ? 0 : 1 }
      value.monitoring_status = unavailable ? 'unavailable' : 'ready'
      return value
    }
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(rooms) })
      if (path === '/api/v1/monitor') return route.fulfill({ json: envelope(monitor()) })
      if (path.endsWith('/balance')) return route.fulfill({ json: envelope(balance('18.70')) })
      if (path.endsWith('/consumption')) {
        consumptionReads += 1
        return route.fulfill({ json: envelope(merged(url.searchParams.get('start_date') ?? '', url.searchParams.get('end_date') ?? '')) })
      }
      if (path.endsWith('/monitor-samples')) return route.fulfill({ json: envelope({ items: [], total: 0,
        page: 1, page_size: 10, has_monitor_history: true, snapshot_token: 'synthetic-snapshot', snapshot_expires_at: '2026-10-07T23:59:00+08:00' }) })
      if (path === '/api/v1/overview') {
        const history = merged('2026-09-24', '2026-10-07')
        return route.fulfill({ json: envelope({ viewing_binding_id: a, profile: null, balance: balance('18.70'),
          summary: { yesterday_amount: null, last_14_days_amount: history.summary.amount, known_days: 1, expected_days: 14, complete: false },
          daily_consumption: history, monitor: null, component_status: { profile: 'unavailable', balance: 'ready', history: 'partial', monitor: 'unavailable' } }) })
      }
      return route.fulfill({ status: 404 })
    })
    await page.goto('/overview')
    await expect(page.getByRole('img', { name: /含余额变化估算/ })).toBeVisible()
    await expect(page.getByText(/当天首次余额减少计入前一天/)).toBeVisible()
    await expect(page.locator('.stat-grid')).toContainText('含余额变化估算')
    await page.goto('/details?start_date=2026-09-28&end_date=2026-10-01')
    await expect(page.getByRole('img', { name: /含余额变化估算/ })).toBeVisible()
    await expect(page.getByText(/当天首次余额减少计入前一天/)).toBeVisible()
    await page.getByText('查看图表数据', { exact: true }).click()
    await expect(page.locator('.chart-data')).toContainText('含余额变化估算 ¥1.30')
    await expect(page.locator('.chart-data')).toContainText('—')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (process.env.ELECT_T4_SCREENSHOT_DIR) {
      await mkdir(process.env.ELECT_T4_SCREENSHOT_DIR, { recursive: true })
      await page.screenshot({ path: `${process.env.ELECT_T4_SCREENSHOT_DIR}/consumption-merge-${width}.png`, fullPage: true })
    }
    const before = consumptionReads
    synced = true
    unavailable = true
    await page.getByRole('button', { name: '读取最新采集记录' }).click()
    await expect.poll(() => consumptionReads).toBeGreaterThan(before)
    await expect(page.getByRole('img', { name: '学校消费记录趋势，未知日期保留断点' })).toBeVisible()
    await expect(page.locator('.chart-data')).toContainText('¥2.50')
    await expect(page.locator('.chart-data')).not.toContainText('余额变化估算')
    await expect(page.getByText('监控估算暂时不可用，正在展示已有学校历史。')).toBeVisible()
  })
}

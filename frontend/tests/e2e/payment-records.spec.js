import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { envelope, me } from '../fixtures/t2.js'
import { monitor } from '../fixtures/t3.js'
import { a, balance, consumption, rooms } from '../fixtures/t4.js'

for (const width of [1440, 375]) {
  test(`${width}px 缴费总额、分页、日期联动与不完整结果`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const reads = []
    let partial = false, failed = false
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(rooms) })
      if (path === '/api/v1/monitor') return route.fulfill({ json: envelope({ ...monitor(), binding_id: a }) })
      if (path.endsWith('/balance')) return route.fulfill({ json: envelope(balance('12.34')) })
      if (path.endsWith('/consumption')) return route.fulfill({ json: envelope(consumption(url.searchParams.get('start_date'), url.searchParams.get('end_date'))) })
      if (path.endsWith('/monitor-samples')) return route.fulfill({ json: envelope({ items: [], total: 0, page: 1, page_size: 10, has_monitor_history: false, snapshot_token: 'test' }) })
      if (path.endsWith('/payment-records')) {
        reads.push(url)
        if (failed) return route.fulfill({ status: 503, json: { error: { code: 'SCHOOL_UNAVAILABLE', message: '学校查询暂不可用' } } })
        const items = Array.from({ length: 11 }, (_, i) => ({ id: `12345678901234567${String(i).padStart(2, '0')}`, amount: '0.10', paid_at: '2026-10-01T10:00:00+08:00', created_at: '2026-10-01T09:00:00+08:00', method: i === 0 ? '7' : '1' }))
        return route.fulfill({ json: envelope({ items, total: 11, total_amount: partial ? null : '1.10', known_amount: '1.10', complete: !partial }) })
      }
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND', message: '合成场景未登记接口' } } })
    })
    await page.goto('/details?start_date=2026-10-01&end_date=2026-10-02')
    const panel = page.locator('section.card').filter({ has: page.getByRole('heading', { name: '缴费明细列表' }) })
    await expect(panel.getByText('总缴费 ¥1.10')).toBeVisible()
    await expect(panel.getByText('其他（7）')).toBeVisible()
    const first = reads.length
    await panel.getByRole('button', { name: '下一页' }).click()
    await expect(panel.getByText('第2页')).toBeVisible()
    await expect(panel.getByText('总缴费 ¥1.10')).toBeVisible()
    expect(reads.length).toBe(first)
    await page.getByLabel('开始日期', { exact: true }).fill('2026-09-30')
    expect(reads.length).toBe(first)
    await page.getByRole('button', { name: '应用日期范围' }).click()
    await expect(panel.getByText('第1页')).toBeVisible()
    await expect.poll(() => reads.at(-1)?.searchParams.get('start_date')).toBe('2026-09-30')
    await expect(panel.getByText('总缴费 ¥1.10')).toBeVisible()
    const samples = page.getByRole('heading', { name: '监控采集明细' })
    expect((await panel.boundingBox()).y).toBeGreaterThan((await samples.boundingBox()).y)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (process.env.ELECT_PAYMENT_SCREENSHOTS) {
      await mkdir(process.env.ELECT_PAYMENT_SCREENSHOTS, { recursive: true })
      await page.screenshot({ path: `${process.env.ELECT_PAYMENT_SCREENSHOTS}/${width}-payment-records.png`, fullPage: true })
    }
    partial = true
    await panel.getByRole('button', { name: '读取最新缴费记录' }).click()
    await expect(panel.getByText(/总缴费 —/)).toBeVisible()
    await expect(panel.getByRole('alert')).toContainText('尚未读取完整')
    failed = true
    await panel.getByRole('button', { name: '读取最新缴费记录' }).click()
    await expect(panel.getByText('学校查询暂不可用')).toBeVisible()
    await expect(panel.getByText('正在展示上次成功读取的记录。')).toBeVisible()
  })
}

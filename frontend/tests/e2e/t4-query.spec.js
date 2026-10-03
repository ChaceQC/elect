import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { envelope, me } from '../fixtures/t2.js'
import { monitor } from '../fixtures/t3.js'
import { a, b, balance, consumption, rooms, run, runId, sample } from '../fixtures/t4.js'

const op = '0199a10c-0000-7000-8000-000000000006'
/** @param {import('@playwright/test').Page} page @param {string} name */
async function capture(page, name) {
  if (!process.env.ELECT_T4_SCREENSHOT_DIR) return
  await mkdir(process.env.ELECT_T4_SCREENSHOT_DIR, { recursive: true })
  await page.screenshot({ path: `${process.env.ELECT_T4_SCREENSHOT_DIR}/${name}.png`, fullPage: true })
}
for (const width of [1440, 375]) {
  test(`${width}px：总览独立查看刷新保留目标，历史失败不覆盖对应余额`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      expect(request.method()).toBe('GET')
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(rooms) })
      if (path === '/api/v1/monitor') return route.fulfill({ json: envelope({ ...monitor(), binding_id: a }) })
      if (path.endsWith('/balance')) return route.fulfill({ json: envelope(balance(path.includes(b) ? '98.76' : '12.34')) })
      if (path === '/api/v1/overview') return route.fulfill({ json: envelope({ viewing_binding_id: b,
        profile: { student_id: 'synthetic', default_binding: rooms.items[0], alert_email: null }, balance: balance('98.76'), summary: null, daily_consumption: null,
        monitor: { enabled: true, state: 'active', health: 'unavailable', interval_minutes: 60 },
        component_status: { profile: 'ready', balance: 'stale', history: 'failed', monitor: 'ready' } }) })
      return route.fulfill({ status: 404 })
    })
    await page.goto(`/overview?binding_id=${b}`)
    await expect(page.locator('.balance-amount')).toHaveText('¥98.76')
    await expect(page.getByText('学校历史暂时不可用，余额和监控信息仍可独立读取。')).toBeVisible()
    await page.reload()
    await expect(page.getByLabel('查看寝室')).toHaveValue(b)
    await expect(page.locator('.balance-amount')).toHaveText('¥98.76')
    await expect(page.getByRole('img')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
  test(`${width}px：逐房间余额、统一日期草稿/粒度、未知断点和固定快照分页`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const amounts = { [a]: '12.34', [b]: '98.76' }
    let refreshes = 0, newest = false
    const historyReads = /** @type {URL[]} */ ([])
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), url = new URL(request.url()), path = url.pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: { ...envelope(me), meta: { ...envelope(me).meta, server_time: '2026-10-01T10:00:00+08:00' } } })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(rooms) })
      if (path === '/api/v1/monitor') return route.fulfill({ json: envelope({ ...monitor(), binding_id: a }) })
      if (path.endsWith('/balance')) return route.fulfill({ json: envelope(balance(amounts[path.split('/')[4]])) })
      if (path.endsWith('/balance-refresh')) {
        expect(path.split('/')[4]).toBe(b); refreshes += 1; amounts[b] = '93.12'
        expect(request.headers()['idempotency-key']).toBeTruthy()
        return route.fulfill({ status: 202, json: envelope({ operation_id: op, state: 'accepted', poll_url: `/api/v1/operations/${op}` }) })
      }
      if (path === `/api/v1/operations/${op}`) return route.fulfill({ json: envelope({ id: op, state: 'succeeded' }) })
      if (path.endsWith('/consumption')) {
        historyReads.push(url)
        return route.fulfill({ json: envelope(consumption(url.searchParams.get('start_date') ?? '', url.searchParams.get('end_date') ?? '', /** @type {'day'|'week'|'month'} */ (url.searchParams.get('granularity')))) })
      }
      if (path.endsWith('/monitor-samples')) {
        const number = Number(url.searchParams.get('page'))
        if (number === 2) expect(url.searchParams.get('snapshot_token')).toBe('synthetic-fixed-snapshot')
        return route.fulfill({ json: envelope({ items: number === 1 ? Array.from({ length: 10 }, (_, i) => sample(i)) : [sample(10)], page: number, page_size: 10,
          total: newest && !url.searchParams.get('snapshot_token') ? 13 : 11, has_monitor_history: true,
          snapshot_token: 'synthetic-fixed-snapshot', snapshot_expires_at: '2026-10-01T10:30:00+08:00' }) })
      }
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND', message: '测试未登记接口' } } })
    })
    await page.goto('/details')
    await expect(page.getByText('¥12.34', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('img', { name: '学校消费记录趋势，未知日期保留断点' })).toBeVisible()
    await expect(page.getByText('数据不完整', { exact: false })).toBeVisible()
    const count = historyReads.length
    await page.getByLabel('开始日期', { exact: true }).fill('2026-09-20')
    await page.getByLabel('结束日期', { exact: true }).fill('2026-09-30')
    expect(historyReads.length).toBe(count)
    await expect(page.getByText(/待应用/)).toBeVisible()
    await page.getByRole('button', { name: '应用日期范围' }).click()
    await expect.poll(() => historyReads.at(-1)?.searchParams.get('start_date')).toBe('2026-09-20')
    await page.getByRole('group', { name: '图表粒度' }).getByRole('button', { name: '周', exact: true }).click()
    await expect.poll(() => historyReads.at(-1)?.searchParams.get('granularity')).toBe('week')
    expect(historyReads.at(-1)?.searchParams.get('end_date')).toBe('2026-09-30')
    await page.reload()
    await expect(page.getByLabel('开始日期', { exact: true })).toHaveValue('2026-09-20')
    await expect(page.getByLabel('结束日期', { exact: true })).toHaveValue('2026-09-30')
    await expect(page.getByRole('group', { name: '图表粒度' }).getByRole('button', { name: '周', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(page.getByText('第2页')).toBeVisible()
    await expect(page.getByText('—', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('第2页')).toBeVisible()
    newest = true
    await page.getByRole('button', { name: '读取最新采集记录' }).click()
    await expect(page.getByText('第1页')).toBeVisible()
    await expect(page.getByText('共 13 条')).toBeVisible()
    await page.getByLabel('查看寝室').selectOption(b)
    await expect(page.locator('.balance-amount')).toHaveText('¥98.76')
    await page.getByRole('button', { name: '刷新学校余额' }).click()
    await expect(page.locator('.balance-amount')).toHaveText('¥93.12')
    expect(refreshes).toBe(1)
    await expect(page.getByText('独立查看不会修改默认寝室或监控目标。')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await capture(page, `t4-details-${width}`)
  })

  test(`${width}px：立即采集、取消版本、刷新恢复与已保存开关独立`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let started = false, writes = 0, cancelled = false
    let state = /** @type {import('../../src/api/generated').components['schemas']['Run']['state']} */ ('running')
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(rooms) })
      if (path === '/api/v1/monitor') return route.fulfill({ json: envelope({ ...monitor(), binding_id: a, current_run: started && !cancelled ? run(state) : null, last_run: started ? run(state) : null }) })
      if (path === '/api/v1/monitor/runs') {
        started = true; writes += 1
        return route.fulfill({ status: 202, json: envelope({ run_id: runId, version: 1, state: 'pending', poll_url: `/api/v1/monitor/runs/${runId}` }) })
      }
      if (path === `/api/v1/monitor/runs/${runId}`) return route.fulfill({ json: envelope(run(state)) })
      if (path.endsWith('/cancel')) {
        expect(request.postDataJSON()).toEqual({ expected_version: 2 })
        state = 'cancel_requested'
        return route.fulfill({ json: envelope(run(state)) })
      }
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND' } } })
    })
    await page.goto('/monitor')
    await page.getByText('运行与提醒状态', { exact: false }).click()
    await page.getByRole('button', { name: '立即采集', exact: true }).click()
    await expect(page.getByText('正在采集', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '取消本次采集', exact: true }).click()
    await expect(page.getByText('正在结束本次请求')).toBeVisible()
    await page.reload()
    await page.getByText('运行与提醒状态', { exact: false }).click()
    await expect(page.getByText('正在结束本次请求')).toBeVisible()
    state = 'cancelled'; cancelled = true
    await page.getByRole('button', { name: '读取最新运行', exact: true }).click()
    await expect(page.getByText('本次已取消')).toBeVisible()
    await expect(page.getByLabel('启用监控')).toBeChecked()
    expect(writes).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await capture(page, `t4-monitor-${width}`)
  })
}

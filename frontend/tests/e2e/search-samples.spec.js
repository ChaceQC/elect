import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { envelope } from '../fixtures/t2.js'
import { sample } from '../fixtures/t4.js'
import { visualFixture } from '../fixtures/visual.js'

for (const width of [1440, 375]) {
  test(`${width}px：搜索焦点覆盖整个搜索框`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const unexpected = await visualFixture(page)
    await page.goto('/rooms')
    const input = page.getByPlaceholder('搜索已绑定的楼栋、寝室号')
    const box = page.locator('.search-box')
    await input.click()
    await expect(input).toBeFocused()
    await expect(box).toHaveCSS('outline-width', '3px')
    await expect(input).toHaveCSS('outline-style', 'none')
    const outer = await box.boundingBox(), icon = await box.locator('svg').boundingBox()
    expect(icon.x).toBeGreaterThan(outer.x)
    expect(icon.x + icon.width).toBeLessThan(outer.x + outer.width)
    await page.keyboard.press('Tab')
    await expect(box).toHaveCSS('outline-style', 'none')
    await page.keyboard.press('Shift+Tab')
    await expect(input).toBeFocused()
    await expect(box).toHaveCSS('outline-width', '3px')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (process.env.ELECT_SEARCH_SCREENSHOT_DIR) {
      await mkdir(process.env.ELECT_SEARCH_SCREENSHOT_DIR, { recursive: true })
      await page.screenshot({ path: `${process.env.ELECT_SEARCH_SCREENSHOT_DIR}/${width}-rooms-focus.png`, fullPage: true })
    }
    expect(unexpected).toEqual([])
  })

  test(`${width}px：采集超过50条后首页更新，隐藏暂停且后续分页固定`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.clock.install()
    const unexpected = await visualFixture(page)
    let total = 50
    const snapshots = new Map()
    const reads = []
    await page.route('**/api/v1/room-bindings/*/monitor-samples?**', async route => {
      expect(route.request().method()).toBe('GET')
      const params = new URL(route.request().url()).searchParams
      const number = Number(params.get('page')), token = params.get('snapshot_token')
      reads.push({ number, token })
      if (!token) {
        expect(number).toBe(1)
        const members = Array.from({ length: total }, (_, i) => sample(total - 1 - i))
        snapshots.set(`synthetic-snapshot-${snapshots.size}`, members)
      }
      const current = token ?? `synthetic-snapshot-${snapshots.size - 1}`
      const members = snapshots.get(current)
      expect(members).toBeTruthy()
      return route.fulfill({ json: envelope({ items: members.slice((number - 1) * 10, number * 10),
        total: members.length, page: number, page_size: 10, has_monitor_history: true,
        snapshot_token: current, snapshot_expires_at: new Date(Date.now() + 1_800_000).toISOString() }) })
    })
    await page.goto('/details')
    await expect(page.getByText('共 50 条', { exact: true })).toBeVisible()
    total = 51
    await page.clock.runFor(61_000)
    await expect(page.getByText('共 51 条', { exact: true })).toBeVisible()
    expect(reads.at(-1).token).toBeNull()
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(page.getByText('第2页', { exact: true })).toBeVisible()
    const fixed = reads.at(-1).token, count = reads.length
    expect(fixed).toBeTruthy()
    total = 52
    await page.clock.runFor(61_000)
    expect(reads.length).toBe(count)
    await expect(page.getByText('共 51 条', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '上一页', exact: true }).click()
    await expect(page.getByText('共 52 条', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(page.getByText('第2页', { exact: true })).toBeVisible()
    await expect(page.getByText('共 52 条', { exact: true })).toBeVisible()
    expect(reads.at(-1).token).not.toBe(fixed)
    await page.getByRole('button', { name: '读取最新采集记录' }).click()
    await expect(page.getByText('第1页', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '读取最新采集记录' })).toBeEnabled()
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
      document.dispatchEvent(new Event('visibilitychange', { bubbles: true }))
    })
    const hiddenReads = reads.length
    total = 53
    await page.clock.runFor(61_000)
    expect(reads.length).toBe(hiddenReads)
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
      document.dispatchEvent(new Event('visibilitychange', { bubbles: true }))
    })
    await expect(page.getByText('共 53 条', { exact: true })).toBeVisible()
    expect(reads.at(-1).token).toBeNull()
    expect(unexpected).toEqual([])
  })
}

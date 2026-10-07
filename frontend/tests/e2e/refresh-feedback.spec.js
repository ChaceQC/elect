import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { visualFixture } from '../fixtures/visual.js'
import { envelope } from '../fixtures/t2.js'

for (const width of [1440, 375]) {
  test(`${width}px：刷新只显示动画、完成停止，错误仍可见`, async ({ page }) => {
    await page.clock.install()
    await page.setViewportSize({ width, height: 1000 })
    await visualFixture(page)
    const id = '0199a10c-0000-7000-8000-000000000090'
    let state = 'running'
    await page.route('**/api/v1/room-bindings/*/history-sync', route => route.fulfill({ status: 202,
      json: envelope({ operation_id: id, state: 'accepted', poll_url: `/api/v1/operations/${id}` }) }))
    await page.route('**/api/v1/operations/' + id, route => route.fulfill({ json: envelope({ id, type: 'history_sync', state }) }))
    await page.goto('/details')
    await expect(page.locator('.consumption-chart canvas')).toBeVisible()
    const refresh = page.getByRole('button', { name: '同步所选范围的学校历史' })
    await expect(refresh).toBeDisabled()
    await expect(refresh).toHaveAttribute('aria-busy', 'true')
    const spinner = refresh.locator('svg')
    await expect(spinner).toHaveCSS('animation-name', 'refresh-spin')
    await expect(page.getByText(/查询已受理|正在从学校读取|本次同步范围/)).toHaveCount(0)
    await expect(refresh.locator('span')).toHaveClass('sr-only')
    expect((await refresh.boundingBox()).width).toBeLessThan(75)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (process.env.ELECT_REFRESH_SCREENSHOT_DIR) {
      await mkdir(process.env.ELECT_REFRESH_SCREENSHOT_DIR, { recursive: true })
      await page.screenshot({ path: `${process.env.ELECT_REFRESH_SCREENSHOT_DIR}/${width}-refresh.png`, fullPage: true })
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await expect(spinner).toHaveCSS('animation-name', 'none')
    state = 'succeeded'
    await page.clock.fastForward(2100)
    await expect(refresh).toBeEnabled()
    await expect(refresh).toHaveAttribute('aria-busy', 'false')
    await expect(page.getByText('查询已完成')).toHaveCount(0)
    state = 'failed'
    await page.reload()
    await expect(page.getByText('本次查询未完成，已保留最近成功数据。')).toBeVisible()
  })
}

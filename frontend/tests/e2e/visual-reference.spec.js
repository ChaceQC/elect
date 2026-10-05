import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { visualFixture } from '../fixtures/visual.js'
import { envelope } from '../fixtures/t2.js'

test.use({ locale: 'zh-CN' })

/** @param {import('@playwright/test').Page} page @param {number} width @param {string} state */
async function capture(page, width, state) {
  const directory = process.env.ELECT_UI_SCREENSHOT_DIR
  if (!directory) return
  await mkdir(directory, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: `${directory}/${width}-${state}.png`, fullPage: true, animations: 'disabled' })
}
for (const width of [1440, 375]) {
  test(`${width}px：参考布局、四页与弹窗截图，日历键盘和账户可用`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const errors = [], unexpected = await visualFixture(page)
    page.on('pageerror', error => errors.push(error.message))
    await page.goto('/overview')
    await expect(page.locator('.consumption-chart canvas')).toBeVisible()
    await expect(page.locator('.balance-amount')).toHaveText('¥86.42')
    const nav = await page.getByRole('navigation').boundingBox()
    const main = await page.locator('main').boundingBox()
    // 防止再次退回手机底部导航或桌面满宽纵向堆叠。
    if (width < 760) expect(nav.y + nav.height).toBeLessThan(main.y)
    else expect(main.x).toBe(238)
    await capture(page, width, 'overview')
    for (const [title, name] of [['电费明细', 'details'], ['选择与绑定', 'rooms'], ['监控与预警', 'monitor']]) {
      await page.getByRole('link', { name: title, exact: true }).click()
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
      if (name === 'details') {
        await expect(page.locator('.consumption-chart canvas')).toBeVisible()
        const amount = await page.locator('.balance-amount').boundingBox()
        const payment = await page.getByRole('button', { name: '充值电费' }).boundingBox()
        expect(payment.x).toBeGreaterThan(amount.x)
        expect(payment.y).toBeLessThan(amount.y + amount.height)
      }
      if (name === 'rooms') await expect(page.locator('.room-card')).toHaveCount(1)
      if (name === 'monitor') await expect(page.getByLabel('提醒邮箱', { exact: true })).toHaveValue('fixture@example.invalid')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await capture(page, width, name)
    }
    await page.getByRole('link', { name: '选择与绑定', exact: true }).click()
    await page.getByRole('button', { name: '新增绑定', exact: true }).click()
    await expect(page.getByRole('button', { name: '合成甲楼', exact: true })).toBeVisible()
    await capture(page, width, 'binding')
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '新增绑定', exact: true })).toBeFocused()
    await page.getByRole('link', { name: '电费明细', exact: true }).click()
    await page.getByRole('button', { name: '打开开始日期日历' }).click()
    await expect(page.getByRole('button', { name: '2026-09-02', exact: true })).toBeFocused()
    await capture(page, width, 'calendar')
    await page.keyboard.press('ArrowLeft')
    await page.keyboard.press('ArrowLeft')
    await expect(page.getByRole('button', { name: '2026-08-31', exact: true })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '打开开始日期日历' })).toBeFocused()
    await expect(page.getByRole('button', { name: '充值电费' })).toBeDisabled()
    await expect(page.getByText('支付暂未开放', { exact: true })).toBeVisible()
    await capture(page, width, 'payment-unavailable')
    await page.getByRole('button', { name: '我的账户' }).click()
    await page.getByRole('button', { name: '退出应用', exact: true }).click()
    await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
    await expect(page.getByAltText('学校算式验证码')).toBeVisible()
    await capture(page, width, 'login')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(errors).toEqual([])
    expect(unexpected).toEqual([])
  })
}

test('成功空绑定显示参考引导，失败状态不伪装为首次绑定', async ({ page }) => {
  await visualFixture(page)
  let state = 'empty'
  await page.route('**/api/v1/room-bindings?*', route => route.fulfill({ json: envelope({
    items: [], page: 1, page_size: 100, total: 0, default_binding_id: null, preference_version: 1, binding_write_enabled: true,
    sync_status: state, last_synced_at: '2026-10-01T10:00:00+08:00', pending_operations: [], pending_operations_truncated: false,
  }) }))
  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: '先找到你的寝室' })).toBeVisible()
  await expect(page.locator('.balance-amount')).toHaveCount(0)
  await page.getByRole('link', { name: '绑定我的寝室' }).click()
  await expect(page.getByRole('dialog', { name: '新增绑定寝室' })).toBeVisible()
  await page.keyboard.press('Escape')
  state = 'failed'
  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: '总览', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '先找到你的寝室' })).toHaveCount(0)
})

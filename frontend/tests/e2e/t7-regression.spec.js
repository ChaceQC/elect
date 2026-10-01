import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { agreement, captcha, envelope, me, requestId } from '../fixtures/t2.js'
import { monitor } from '../fixtures/t3.js'
import { a, balance, consumption, emptyOverview, rooms, sample } from '../fixtures/t4.js'

/** @param {import('@playwright/test').BrowserContext} context */
async function fixture(context) {
  let user = me
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (path === '/api/v1/auth/me') return route.fulfill(user ? { json: envelope(user) } : {
      status: 401, json: { error: { code: 'APP_SESSION_EXPIRED' }, meta: { request_id: requestId } } })
    if (path === '/api/v1/auth/logout') { user = null; return route.fulfill({ status: 204 }) }
    if (path === '/api/v1/auth/agreement') return route.fulfill({ json: envelope(agreement) })
    if (path === '/api/v1/auth/captcha') return route.fulfill({ json: envelope(captcha()) })
    if (path === '/api/v1/auth/login') {
      user = { ...me, id: '0199a10c-0000-7000-8000-000000000099', student_id: 'synthetic-second' }
      return route.fulfill({ json: envelope({ user, bootstrap: { rooms_state: 'ready' } }) })
    }
    if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(user?.id === me.id ? rooms : {
      ...rooms, items: [{ ...rooms.items[0], display_name: '第二账号的寝室' }], total: 1 }) })
    if (path === '/api/v1/overview') return route.fulfill({ json: envelope(emptyOverview) })
    if (path === `/api/v1/room-bindings/${a}`) return route.fulfill({ json: envelope(rooms.items[0]) })
    if (path.endsWith('/balance')) return route.fulfill({ json: envelope(balance('12.34')) })
    if (path.endsWith('/consumption')) return route.fulfill({ json: envelope(consumption(
      url.searchParams.get('start_date'), url.searchParams.get('end_date'))) })
    if (path.endsWith('/monitor-samples')) return route.fulfill({ json: envelope({ binding_id: a,
      items: [sample(10)], total: 1, page: 1, page_size: 10, has_monitor_history: true, snapshot_token: 'synthetic-snapshot' }) })
    if (path === '/api/v1/monitor') return route.fulfill({ json: envelope(monitor()) })
    if (path === '/api/v1/payments/capabilities') return route.fulfill({ json: envelope({ enabled: false,
      currency: 'CNY', min_amount: '1.00', max_amount: '500.00', amount_step: '1.00',
      presets: [], unresolved_order: null, unavailable_reason: '支付尚未完成真实验收' }) })
    return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND' } } })
  })
}

/** @param {import('@playwright/test').Page} page */
async function noOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [375, 390, 768, 1280, 1440]) {
  test(`${width}px：四页、长错误、账户与支付弹窗可达`, async ({ page, context }) => {
    await fixture(context)
    await page.setViewportSize({ width, height: 900 })
    for (const [path, title] of [['overview', '用电总览'], ['details', '电费明细'], ['rooms', '我的寝室'], ['monitor', '监控提醒']]) {
      await page.goto(`/${path}`)
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
      await noOverflow(page)
      await expect(page.getByRole('button', { name: '我的账户' })).toBeVisible()
    }
    await page.getByRole('button', { name: '我的账户' }).click()
    await page.keyboard.press('Shift+Tab')
    await expect(page.getByRole('button', { name: '退出应用' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('button', { name: '关闭弹窗' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '我的账户' })).toBeFocused()
    await page.goto(`/rooms/${a}`)
    await page.getByRole('button', { name: '充值电费' }).click()
    await expect(page.getByRole('dialog')).toContainText('支付尚未完成真实验收')
    await expect(page.getByRole('button', { name: '确认创建充值订单' })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '充值电费' })).toBeFocused()
    await page.goto('/details')
    await page.getByLabel('开始日期').fill('2027-01-01')
    await expect(page.getByLabel('开始日期')).toHaveAttribute('aria-invalid', 'true')
    const description = await page.getByLabel('开始日期').getAttribute('aria-describedby')
    await expect(page.locator(`[id="${description}"]`)).toBeVisible()
    await noOverflow(page)
    if (process.env.ELECT_T7_SCREENSHOT_DIR) {
      await mkdir(process.env.ELECT_T7_SCREENSHOT_DIR, { recursive: true })
      await page.screenshot({ path: `${process.env.ELECT_T7_SCREENSHOT_DIR}/${width}-details.png`, fullPage: true })
    }
    await page.route('**/api/v1/monitor', route => route.fulfill({ status: 503,
      json: { error: { code: 'DEPENDENCY_UNAVAILABLE', message: '学校暂不可用，请保留当前设置并稍后重试。'.repeat(12), retryable: false } } }))
    await page.goto('/monitor')
    await expect(page.getByRole('alert')).toContainText('学校暂不可用')
    await noOverflow(page)
  })
}

test('双标签页退出与再次登录清理会话、房间和草稿', async ({ context, page }) => {
  await fixture(context)
  const other = await context.newPage()
  await page.goto('/rooms')
  await other.goto('/monitor')
  await other.getByLabel('采集间隔（整数分钟）').fill('75')
  await page.getByRole('button', { name: '我的账户' }).click()
  await page.getByRole('button', { name: '退出应用' }).click()
  await expect(other.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  await expect(other.getByLabel('采集间隔（整数分钟）')).toHaveCount(0)
  await page.getByLabel('学校账号', { exact: true }).fill('synthetic-second')
  await page.getByLabel('学校密码').fill('synthetic-password')
  await page.getByLabel('验证码答案').fill('3')
  await page.getByRole('button', { name: '阅读应用协议' }).click()
  await page.getByRole('button', { name: '我已阅读' }).click()
  await page.getByLabel('我同意应用使用协议').check()
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await other.goto('/rooms')
  await expect(other.getByText('第二账号的寝室', { exact: true })).toBeVisible()
  await expect(other.getByText('合成乙楼 202', { exact: true })).toHaveCount(0)
  await other.goto('/monitor')
  await expect(other.getByLabel('采集间隔（整数分钟）')).toHaveValue('60')
})

test('图表切页释放观察器，缩放等效视口与减少动效可用', async ({ context, page }) => {
  await fixture(context)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 640, height: 450 })
  await page.addInitScript(() => {
    const Original = window.ResizeObserver
    const observed = new Set()
    Object.defineProperty(window, 't7Observers', { get: () => observed.size })
    window.ResizeObserver = class extends Original {
      observe(element, options) { observed.add(this); super.observe(element, options) }
      disconnect() { observed.delete(this); super.disconnect() }
    }
  })
  await page.goto('/details')
  await expect(page.locator('.consumption-chart canvas')).toBeVisible()
  const count = await page.evaluate(() => Reflect.get(window, 't7Observers'))
  for (let i = 0; i < 5; i++) {
    await page.getByRole('link', { name: '我的寝室', exact: true }).click()
    await expect.poll(() => page.evaluate(() => Reflect.get(window, 't7Observers'))).toBe(0)
    await page.getByRole('link', { name: '电费明细', exact: true }).click()
    await expect(page.locator('.consumption-chart canvas')).toBeVisible()
    expect(await page.evaluate(() => Reflect.get(window, 't7Observers'))).toBe(count)
  }
  await page.getByText('查看图表数据', { exact: true }).click()
  await expect(page.locator('.chart-data')).toContainText('部分数据')
  await noOverflow(page)
})

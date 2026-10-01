import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { bindings, envelope, me } from '../fixtures/t2.js'
import { binding, bindingId, capability, order, orderId } from '../fixtures/t6.js'

for (const width of [1440, 375]) {
  test(`${width}px：能力规则、建单重复防护、未知订单重开和刷新恢复`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let accepted = false, writes = 0, amount = '20.00'
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope({ ...bindings,
        items: [binding], total: 1, default_binding_id: bindingId }) })
      if (path === '/api/v1/room-candidates/buildings') return route.fulfill({ json: envelope({ items: [] }) })
      if (path === '/api/v1/payments/capabilities') return route.fulfill({ json: envelope({ ...capability,
        unresolved_order: accepted ? { ...order, amount } : null }) })
      if (path === '/api/v1/payment-orders') {
        writes += 1; amount = request.postDataJSON().amount
        expect(request.postDataJSON().binding_id).toBe(bindingId)
        accepted = true
        return route.fulfill({ status: 202, json: envelope({ order_id: orderId, state: 'created', poll_url: `/api/v1/payment-orders/${orderId}` }) })
      }
      if (path === `/api/v1/payment-orders/${orderId}`) return route.fulfill({ json: envelope({ ...order, amount }) })
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND', message: '合成未使用接口' } } })
    })
    await page.goto('/rooms')
    await page.getByRole('button', { name: '充值电费' }).click()
    await expect(page.getByText(/应用充值规则/)).toBeVisible()
    await page.getByLabel('充值金额（元）').fill('1.01')
    await expect(page.getByRole('button', { name: '确认创建充值订单' })).toBeDisabled()
    await page.getByLabel('充值金额（元）').fill('30')
    await page.getByRole('button', { name: '确认创建充值订单' }).click()
    await expect(page.getByText('支付状态尚未确认')).toBeVisible()
    await expect(page.getByRole('dialog')).toContainText('¥30.00')
    await expect(page.getByText('学校已确认支付')).toHaveCount(0)
    await page.getByRole('button', { name: '关闭弹窗' }).click()
    await page.getByRole('button', { name: '充值电费' }).click()
    await expect(page.getByText('支付状态尚未确认')).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: '充值电费' }).click()
    await expect(page.getByText('支付状态尚未确认')).toBeVisible()
    await page.getByRole('button', { name: '查询支付结果' }).click()
    expect(writes).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const directory = process.env.ELECT_T6_SCREENSHOT_DIR
    if (directory) {
      await mkdir(directory, { recursive: true })
      await page.screenshot({ path: `${directory}/${width}-payment-unknown.png`, fullPage: true })
    }
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '充值电费' })).toBeFocused()
  })
}

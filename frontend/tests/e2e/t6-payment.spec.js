import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { bindings, envelope, me } from '../fixtures/t2.js'
import { binding, bindingId, capability, order, orderId } from '../fixtures/t6.js'

for (const width of [1440, 375]) {
  test(`${width}px：能力规则、建单重复防护、未知订单重开和刷新恢复`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let accepted = false, cancelled = false, cancels = 0, writes = 0, reads = 0, amount = '20.00'
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope({ ...bindings,
        items: [binding], total: 1, default_binding_id: bindingId }) })
      if (path === '/api/v1/room-candidates/buildings') return route.fulfill({ json: envelope({ items: [] }) })
      if (path === '/api/v1/payments/capabilities') return route.fulfill({ json: envelope({ ...capability,
        unresolved_order: accepted && !cancelled ? { ...order, amount } : null }) })
      if (path === '/api/v1/payment-orders') {
        writes += 1; amount = request.postDataJSON().amount
        expect(request.postDataJSON().binding_id).toBe(bindingId)
        accepted = true
        return route.fulfill({ status: 202, json: envelope({ order_id: orderId, state: 'created', poll_url: `/api/v1/payment-orders/${orderId}` }) })
      }
      const current = { ...order, amount, version: cancelled ? 2 : 1,
        cancelled_at: cancelled ? '2026-10-02T03:00:00+08:00' : null }
      if (path === `/api/v1/payment-orders/${orderId}`) { reads += 1; return route.fulfill({ json: envelope(current) }) }
      if (path === `/api/v1/payment-orders/${orderId}/cancel`) {
        expect(request.postDataJSON()).toEqual({ expected_version: 1 })
        expect(request.headers()['x-csrf-token']).toBe(me.csrf_token)
        cancelled = true; cancels += 1
        return route.fulfill({ json: envelope({ ...current, version: 2, cancelled_at: '2026-10-02T03:00:00+08:00' }) })
      }
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND', message: '合成未使用接口' } } })
    })
    await page.goto('/rooms')
    await page.getByRole('button', { name: '充值电费' }).click()
    await expect(page.getByText(/每次递增/)).toBeVisible()
    await page.getByLabel('充值金额（元）').fill('1.01')
    await expect(page.getByRole('button', { name: '确认创建充值订单' })).toBeDisabled()
    await page.getByLabel('充值金额（元）').fill('30')
    await page.getByRole('button', { name: '确认创建充值订单' }).click()
    await expect(page.getByText('支付状态尚未确认')).toBeVisible()
    await expect(page.getByRole('dialog')).toContainText('¥30.00')
    await expect(page.getByText('学校已确认支付')).toHaveCount(0)
    await page.getByRole('button', { name: '关闭弹窗' }).click()
    await page.getByRole('button', { name: '查看原充值订单' }).click()
    await expect(page.getByText('支付状态尚未确认')).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: '查看原充值订单' }).click()
    await expect(page.getByText('支付状态尚未确认')).toBeVisible()
    await expect(page.getByRole('button', { name: '查询支付结果' })).toHaveCount(0)
    const previousReads = reads
    await expect.poll(() => reads).toBeGreaterThan(previousReads)
    expect(writes).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const directory = process.env.ELECT_T6_SCREENSHOT_DIR
    if (directory) {
      await mkdir(directory, { recursive: true })
      await page.screenshot({ path: `${directory}/${width}-payment-unknown.png`, fullPage: true })
    }
    await page.getByRole('button', { name: '停止处理此订单', exact: true }).click()
    await page.getByRole('button', { name: '确认停止处理', exact: true }).click()
    await expect(page.getByRole('heading', { name: '本系统已停止处理' })).toBeVisible()
    await page.getByRole('button', { name: '重新选择充值金额' }).click()
    await expect(page.getByLabel('充值金额（元）')).toHaveValue('1')
    expect(cancels).toBe(1)
    expect(writes).toBe(1)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '充值电费' })).toBeFocused()
  })
}

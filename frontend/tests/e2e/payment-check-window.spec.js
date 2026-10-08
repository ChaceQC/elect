import { expect, test } from '@playwright/test'
import { visualFixture } from '../fixtures/visual.js'
import { envelope } from '../fixtures/t2.js'
import { capability, order, orderId } from '../fixtures/t6.js'

for (const width of [1440, 375]) {
  test(`订单到期暂停、重开不恢复、显式恢复原订单 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.clock.install()
    await visualFixture(page)
    let current = { ...order, qr_status: 'generating', check_paused: false,
      check_deadline_at: '2026-10-08T14:15:00+08:00' }
    let reads = 0, qrReads = 0, creates = 0
    const resumes = []
    await page.route('**/api/v1/payments/capabilities?*', route => route.fulfill({ json: envelope({ ...capability, unresolved_order: order }) }))
    await page.route('**/api/v1/payment-orders', route => { creates += 1; return route.abort() })
    await page.route(`**/api/v1/payment-orders/${orderId}`, route => {
      reads += 1
      return route.fulfill({ json: envelope(current) })
    })
    await page.route(`**/api/v1/payment-orders/${orderId}/qr`, route => {
      qrReads += 1
      return route.fulfill({ status: 202, json: envelope({ order_id: orderId, qr_status: 'generating',
        poll_url: `/api/v1/payment-orders/${orderId}/qr`, retry_after_seconds: 5 }) })
    })
    await page.route(`**/api/v1/payment-orders/${orderId}/resume-check`, route => {
      resumes.push(route.request().postDataJSON())
      current = { ...current, version: 2, check_paused: false, qr_status: 'unknown',
        check_deadline_at: '2026-10-08T14:30:00+08:00' }
      // 手机场景模拟已受理但响应丢失，前端只GET原订单对账。
      return width === 375 ? route.abort() : route.fulfill({ json: envelope(current) })
    })
    await page.goto('/rooms')
    await page.getByRole('button', { name: '查看原充值订单' }).click()
    await expect(page.getByText('正在取得原订单二维码…')).toBeVisible()
    current = { ...current, check_paused: true }
    await page.clock.fastForward(2100)
    const resume = page.getByRole('button', { name: '继续核对原订单' })
    await expect(resume).toBeVisible()
    await expect(page.getByText('自动核对已达到时限并暂停，原订单仍保留，学校支付结果尚未确认。')).toBeVisible()
    await expect(page.getByText('正在取得原订单二维码…')).toHaveCount(0)
    const stoppedReads = reads, stoppedQrReads = qrReads
    await page.clock.fastForward(120_000)
    expect(reads).toBe(stoppedReads)
    expect(qrReads).toBe(stoppedQrReads)
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '查看原充值订单' }).click()
    await expect(resume).toBeVisible()
    expect(resumes).toEqual([])
    expect(creates).toBe(0)
    await expect(page.getByRole('button', { name: '停止处理此订单' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`payment-paused-${width}.png`), fullPage: true })
    await resume.click()
    await expect(resume).toHaveCount(0)
    await expect(page.getByText('学校结果尚未确认，后台会继续核对原订单。')).toBeVisible()
    expect(resumes).toEqual([{ expected_version: 1 }])
    expect(creates).toBe(0)
    const resumedReads = reads
    await page.clock.fastForward(2100)
    await expect.poll(() => reads).toBeGreaterThan(resumedReads)
    current = { ...current, state: 'paid_confirmed', paid_confirmed: true, balance_refresh_state: 'succeeded' }
    await page.clock.fastForward(2100)
    await expect(page.getByText('学校已确认支付')).toBeVisible()
    const completedReads = reads
    await page.clock.fastForward(60_000)
    expect(reads).toBe(completedReads)
  })
}

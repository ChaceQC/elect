import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { agreement, captcha, envelope, me } from '../fixtures/t2.js'
import { monitor } from '../fixtures/t3.js'
import { a, balance, rooms } from '../fixtures/t4.js'

for (const width of [1440, 375]) {
  test(`${width}px：学校资料离线仍可读缓存和关闭监控，恢复后加载资料，撤销仍退出`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let online = false, revoked = false, sessionCalls = 0, profileCalls = 0, closes = 0
    let current = { ...monitor(), binding_id: a }
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      const send = data => route.fulfill({ json: envelope(data) })
      if (path === '/api/v1/auth/session') {
        sessionCalls += 1
        return revoked ? route.fulfill({ status: 401, json: { error: { code: 'APP_SESSION_EXPIRED' } } })
          : send({ id: me.id, csrf_token: me.csrf_token, consent: me.consent })
      }
      if (path === '/api/v1/auth/me') {
        profileCalls += 1
        return revoked ? route.fulfill({ status: 401, json: { error: { code: 'APP_SESSION_EXPIRED' } } })
          : online ? send(me) : route.fulfill({ status: 503, json: { error: { code: 'DEPENDENCY_UNAVAILABLE' } } })
      }
      if (path === '/api/v1/auth/agreement') return send(agreement)
      if (path === '/api/v1/auth/captcha') return send(captcha())
      if (path === '/api/v1/room-bindings') return send({ ...rooms, binding_write_enabled: true })
      if (path === '/api/v1/monitor' && request.method() === 'PATCH') {
        expect(request.headers()['x-csrf-token']).toBe(me.csrf_token)
        expect(request.postDataJSON()).toEqual({ enabled: false, expected_version: current.version })
        closes += 1
        current = { ...current, version: current.version + 1, state: 'disabled', config: { ...current.config, enabled: false } }
        return send(current)
      }
      if (path === '/api/v1/monitor') return send(current)
      if (path.endsWith('/balance')) return send(balance('12.34'))
      if (path === '/api/v1/payments/capabilities') return send({ enabled: false, min_amount: '1.00', max_amount: '500.00', amount_step: '1.00', currency: 'CNY', unresolved_order: null, unavailable_reason: '测试支付关闭' })
      return route.fulfill({ status: 404 })
    })
    const capture = async state => {
      if (!process.env.ELECT_R6_SCREENSHOT_DIR) return
      await mkdir(process.env.ELECT_R6_SCREENSHOT_DIR, { recursive: true })
      await page.screenshot({ path: `${process.env.ELECT_R6_SCREENSHOT_DIR}/${width}-${state}.png`, fullPage: true })
    }
    await page.goto('/rooms')
    await expect(page.getByRole('heading', { name: '选择与绑定' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '学校资料暂不可用' })).toBeVisible()
    await expect(page.getByText('12.34', { exact: false }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: '新增绑定' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '同步学校绑定' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '充值电费' }).first()).toBeDisabled()
    expect(sessionCalls).toBe(1); expect(profileCalls).toBe(1)
    await capture('offline-rooms')
    await page.getByRole('button', { name: '我的账户' }).click()
    await expect(page.getByText('学校账号：暂不可用')).toBeVisible()
    await expect(page.getByRole('button', { name: '重新学校认证' })).toBeDisabled()
    await capture('offline-account')
    await page.keyboard.press('Escape')
    await page.getByRole('link', { name: '监控与预警' }).click()
    await expect(page.getByRole('heading', { name: '监控与预警' })).toBeVisible()
    await page.getByRole('checkbox', { name: '启用监控' }).uncheck()
    await page.getByRole('button', { name: '保存设置' }).click()
    await expect(page.getByRole('checkbox', { name: '启用监控' })).not.toBeChecked()
    await expect(page.getByText('当前：已关闭', { exact: false })).toBeVisible()
    expect(closes).toBe(1)
    await capture('offline-monitor')
    online = true
    await page.getByRole('button', { name: '重新加载学校资料' }).click()
    await expect(page.getByRole('heading', { name: '学校资料暂不可用' })).toHaveCount(0)
    await page.getByRole('button', { name: '我的账户' }).click()
    await expect(page.getByText(`学校账号：${me.student_id}`)).toBeVisible()
    await expect(page.getByRole('button', { name: '重新学校认证' })).toBeEnabled()
    await capture('recovered-account')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    revoked = true
    await page.reload()
    await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  })
}

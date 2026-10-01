import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { agreement, bindings, captcha, envelope, me, requestId } from '../fixtures/t2.js'

const operationId = '0199a10c-0000-7000-8000-000000000009'
const binding = { id: '0199a10c-0000-7000-8000-000000000003', room_id: '0199a10c-0000-7000-8000-000000000004',
  building: '合成楼栋', number: '001', display_name: '合成楼栋 001', status: 'active',
  balance: { amount: '25.50', currency: 'CNY', source: 'school_bound_rooms', fetched_at: '2026-10-01T10:00:00+08:00',
    school_observed_at: null, stale: false, refresh_state: 'ready', error_code: null } }

/** @param {import('@playwright/test').Page} page @param {string} name */
async function capture(page, name) {
  const directory = process.env.ELECT_T2_SCREENSHOT_DIR
  if (!directory) return
  await mkdir(directory, { recursive: true })
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true })
}

for (const width of [1440, 375]) {
  test(`${width}px：学校验证码、协议、本人同步、刷新与退出失败恢复`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let logged = false, synced = false, failLogout = true, loginCount = 0
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      if (path === '/api/v1/auth/agreement') return route.fulfill({ json: envelope({ ...agreement, content: agreement.content.repeat(80) }) })
      if (path === '/api/v1/auth/captcha') return route.fulfill({ json: envelope(captcha()) })
      if (path === '/api/v1/auth/me') return route.fulfill(logged ? { json: envelope(me) } : {
        status: 401, json: { error: { code: 'APP_SESSION_EXPIRED' }, meta: { request_id: requestId } } })
      if (path === '/api/v1/auth/login') {
        loginCount += 1
        expect(request.postDataJSON().password).toBe(' test password ')
        expect(request.postDataJSON().credential_use_allowed).toBe(true)
        logged = true
        return route.fulfill({ json: envelope({ user: me, bootstrap: { rooms_state: 'loading', requires_binding: null,
          default_binding_id: null, credential_status: 'active' } }) })
      }
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(synced ? { ...bindings,
        items: [binding], total: 1, sync_status: 'ready' } : { ...bindings, last_synced_at: null, sync_status: 'loading' }) })
      if (path === '/api/v1/room-bindings/sync') { synced = true; return route.fulfill({ status: 202, json: envelope({
        operation_id: operationId, state: 'accepted', poll_url: `/api/v1/operations/${operationId}` }) }) }
      if (path === '/api/v1/auth/logout') {
        expect(request.headers()['x-csrf-token']).toBe('synthetic-csrf')
        if (failLogout) { failLogout = false; return route.fulfill({ status: 503,
          json: { error: { code: 'DEPENDENCY_UNAVAILABLE', message: '合成失败' }, meta: { request_id: requestId } } }) }
        logged = false
        return route.fulfill({ status: 204 })
      }
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND' }, meta: { request_id: requestId } } })
    })
    await page.goto('/rooms')
    await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
    await expect(page.getByAltText('学校算式验证码')).toBeVisible()
    await capture(page, `${width}-login`)
    await page.getByLabel('学校账号', { exact: true }).fill('synthetic')
    await page.getByLabel('学校密码').fill(' test password ')
    await page.getByLabel('验证码答案').fill('3')
    await expect(page.getByLabel('我同意应用使用协议')).not.toBeChecked()
    await expect(page.getByLabel('允许后台使用加密凭据恢复学校认证')).not.toBeChecked()
    await page.getByRole('button', { name: '阅读应用协议' }).click()
    await expect(page.getByRole('button', { name: '我已阅读' })).toBeDisabled()
    await page.locator('.agreement-content').evaluate(element => { element.scrollTop = element.scrollHeight })
    await page.getByRole('button', { name: '我已阅读' }).click()
    await page.getByLabel('我同意应用使用协议').check()
    await page.getByLabel('允许后台使用加密凭据恢复学校认证').check()
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByRole('heading', { name: '我的寝室', exact: true })).toBeVisible()
    await expect(page.getByText('合成楼栋 001', { exact: true })).toBeVisible()
    expect(loginCount).toBe(1)
    await page.reload()
    await expect(page).toHaveURL(/\/rooms$/)
    await expect(page.getByText('合成楼栋 001', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await capture(page, `${width}-rooms`)
    await page.getByRole('button', { name: '我的账户' }).click()
    await page.getByRole('button', { name: '退出应用', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('退出未完成')
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: '退出应用', exact: true }).click()
    await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  })
}

test('验证码过期与学校认证失效提供修复入口，已有页面可访问', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: envelope({ ...me, credential_status: 'requires_reauth' }) }))
  await page.route('**/api/v1/room-bindings?*', route => route.fulfill({ json: envelope(bindings) }))
  await page.route('**/api/v1/auth/agreement', route => route.fulfill({ json: envelope(agreement) }))
  await page.route('**/api/v1/auth/captcha', route => route.fulfill({ json: envelope({ ...captcha(),
    expires_at: new Date(Date.now() - 1000).toISOString() }) }))
  await page.goto('/details')
  await expect(page.getByRole('heading', { name: '电费明细' })).toBeVisible()
  await page.getByRole('button', { name: '重新认证', exact: true }).click()
  await page.getByRole('button', { name: '重新学校认证', exact: true }).click()
  await expect(page.getByText('验证码已过期，请换一张。')).toBeVisible()
  await expect(page.getByRole('button', { name: '重新认证', exact: true }).last()).toBeDisabled()
})

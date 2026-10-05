import { expect, test } from '@playwright/test'
import { bindings, envelope } from '../fixtures/t2.js'

const user = { id: '0199a10c-0000-7000-8000-000000000001', student_id: 'synthetic', school: '合成测试学校',
  csrf_token: 'synthetic-csrf', credential_status: 'active', credential_version: 1,
  credential_revoke_operation: null,
  consent: { agreement_version: 'test', accepted_at: '2026-10-01T10:00:00+08:00',
    credential_use_allowed: true, revoked_at: null } }

for (const width of [1440, 375]) {
  test(`${width}px：直达路由、前进后退、账户入口与键盘弹窗`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { data: user, meta: { request_id: user.id } } }))
    await page.route('**/api/v1/room-bindings?*', route => route.fulfill({ json: envelope(bindings) }))
    await page.goto('/details?start=2026-10-01')
    await expect(page.getByRole('heading', { name: '电费明细' })).toBeVisible()
    await page.getByRole('link', { name: '选择与绑定', exact: true }).click()
    await expect(page.getByRole('heading', { name: '选择与绑定' })).toBeVisible()
    await page.goBack()
    await expect(page).toHaveURL(/\/details\?start=2026-10-01/)
    await page.reload()
    await expect(page.getByRole('heading', { name: '电费明细' })).toBeVisible()
    await page.getByRole('button', { name: '我的账户' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Shift+Tab')
    await expect(page.getByRole('button', { name: '退出应用' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await expect(page.getByRole('button', { name: '我的账户' })).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('服务尚未开放时显示持久提示，不出现模拟业务成功', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 403,
    json: { error: { code: 'FEATURE_DISABLED' }, meta: { request_id: user.id } } }))
  await page.goto('/overview')
  await expect(page.getByRole('alert')).toContainText('登录服务尚未开放')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('button', { name: '重新检查' })).toBeVisible()
})

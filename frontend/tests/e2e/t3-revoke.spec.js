import { expect, test } from '@playwright/test'
import { bindings, envelope, me } from '../fixtures/t2.js'

for (const width of [1440, 375]) {
  test(width + 'px：账户没有撤回按钮，旧操作仍能读取终态', async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const id = '0199a10c-0000-7000-8000-000000000012'
    let done = false
    await page.route('**/api/v1/**', async route => {
      expect(route.request().method()).toBe('GET')
      const path = new URL(route.request().url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope({ ...me,
        credential_status: done ? 'revoked' : 'revoking', credential_revoke_operation: done ? null : { id, type: 'credential_revoke', state: 'running' } }) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(bindings) })
      if (path === '/api/v1/operations/' + id) return route.fulfill({ json: envelope({ id, state: done ? 'succeeded' : 'running' }) })
      return route.fulfill({ status: 404 })
    })
    await page.goto('/rooms')
    await page.getByRole('button', { name: '我的账户' }).click()
    await expect(page.getByText('学校认证正在更新…')).toBeVisible()
    await expect(page.getByRole('button', { name: '撤回后台授权', exact: true })).toHaveCount(0)
    done = true
    await page.getByRole('button', { name: '查询认证进度' }).click()
    await expect(page.getByText('学校认证：已撤回')).toBeVisible()
    await expect(page.getByRole('button', { name: '重新学校认证' })).toBeEnabled()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

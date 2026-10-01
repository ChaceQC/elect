import { expect, test } from '@playwright/test'
import { bindings, envelope, me } from '../fixtures/t2.js'

const id = '0199a10c-0000-7000-8000-000000000012'
const summary = { id, type: 'credential_revoke', state: 'running', target_binding_id: null,
  created_at: '2026-10-01T10:00:00+08:00' }

for (const width of [1440, 375]) {
  test(`${width}px：账户撤回确认、202、刷新恢复、终态保持会话`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let phase = 'active', deletes = 0
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope({ ...me,
        credential_status: phase, credential_revoke_operation: phase === 'revoking' ? summary : null,
        consent: { ...me.consent, credential_use_allowed: phase === 'active' } }) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(bindings) })
      if (path === '/api/v1/auth/school-credential') {
        expect(request.method()).toBe('DELETE')
        expect(request.postDataJSON()).toEqual({ expected_version: 1 })
        expect(request.headers()['x-csrf-token']).toBe(me.csrf_token)
        deletes += 1; phase = 'revoking'
        return route.fulfill({ status: 202, json: envelope({ operation_id: id, state: 'accepted', poll_url: `/api/v1/operations/${id}` }) })
      }
      if (path === `/api/v1/operations/${id}`) return route.fulfill({ json: envelope({ ...summary,
        state: phase === 'revoked' ? 'succeeded' : 'running' }) })
      return route.fulfill({ status: 404 })
    })
    await page.goto('/rooms')
    await page.getByRole('button', { name: '我的账户' }).click()
    const action = page.getByRole('button', { name: '撤回后台授权', exact: true })
    await expect(action).toBeDisabled()
    await page.getByLabel('确认撤回后台授权并删除学校凭据').check()
    await action.click()
    await expect(page.getByText('正在撤回后台授权…')).toBeVisible()
    await expect(page.getByText('后台授权已撤回', { exact: true })).toHaveCount(0)
    await page.reload()
    await page.getByRole('button', { name: '我的账户' }).click()
    await expect(page.getByText('正在撤回后台授权…')).toBeVisible()
    expect(deletes).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    phase = 'revoked'
    await page.getByRole('button', { name: '查询撤回进度' }).click()
    await expect(page.getByText('后台授权已撤回', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '退出应用', exact: true })).toBeVisible()
    await expect(page.getByRole('dialog')).toBeVisible()
  })
}

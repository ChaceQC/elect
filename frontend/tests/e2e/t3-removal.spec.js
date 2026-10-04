import { expect, test } from '@playwright/test'
import { bindings, envelope, me } from '../fixtures/t2.js'

const id = '0199a10c-0000-7000-8000-000000000003'
const operation = '0199a10c-0000-7000-8000-000000000019'
const room = { id, room_id: id, display_name: '枫苑5号-402', building: '枫苑5号', number: '402', status: 'active', balance: null }

for (const width of [1440, 375]) {
  test(`${width}px：删除确认、unknown刷新、终态更新与失效独立查看`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let state = '', count = 0
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === `/api/v1/room-bindings/${id}` && route.request().method() === 'DELETE') {
        count += 1; state = 'unknown'
        expect(route.request().headers()['idempotency-key']).toBeTruthy()
        return route.fulfill({ status: 202, json: envelope({ operation_id: operation, state: 'accepted', poll_url: `/api/v1/operations/${operation}` }) })
      }
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope({ ...bindings,
        items: state === 'succeeded' ? [] : [room], total: state === 'succeeded' ? 0 : 1,
        default_binding_id: state === 'succeeded' ? null : id, preference_state: state === 'succeeded' ? 'blocked' : 'ready',
        binding_removal_operation_id: state === 'unknown' ? operation : null,
        pending_operations: state === 'unknown' ? [{ id: operation, type: 'unbind_room', state: 'unknown', target_binding_id: id, created_at: bindings.last_synced_at }] : [] }) })
      if (path === `/api/v1/operations/${operation}`) return route.fulfill({ json: envelope({ id: operation, type: 'unbind_room', state,
        binding_status: state === 'succeeded' ? 'removed' : 'unknown', default_status: state === 'succeeded' ? 'confirmed' : 'switching', error_code: null }) })
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND', message: '已解除' }, meta: { request_id: id } } })
    })
    await page.goto('/rooms')
    await page.getByRole('button', { name: '删除绑定', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('枫苑5号-402')
    await expect(page.getByRole('button', { name: '确认删除绑定' })).toBeDisabled()
    await page.getByLabel('我确认解除该寝室的学校绑定').check()
    await page.getByRole('button', { name: '确认删除绑定' }).click()
    await expect(page.getByText('学校解绑：结果尚未确认')).toBeVisible()
    await expect(page.locator('.room-card')).toHaveCount(1)
    await page.reload()
    await expect(page.getByText('学校解绑：结果尚未确认')).toBeVisible()
    expect(count).toBe(1)
    state = 'succeeded'
    await expect(page.getByRole('button', { name: '查询最新进度' })).toHaveCount(0)
    await expect(page.locator('.room-card')).toHaveCount(0)
    await page.goto(`/rooms/${id}`)
    await expect(page).toHaveURL(/\/rooms$/)
    await expect(page.getByText('所查看的寝室已不可用，已返回本人列表')).toBeVisible()
    expect(count).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

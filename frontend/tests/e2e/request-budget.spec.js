import { expect, test } from '@playwright/test'
import { visualFixture } from '../fixtures/visual.js'
import { envelope } from '../fixtures/t2.js'

test('429等待、刷新浏览器与恢复始终使用原余额请求键', async ({ page }) => {
  await page.clock.install()
  await visualFixture(page)
  const keys = []
  const id = '0199a10c-0000-7000-8000-000000000090'
  await page.route('**/api/v1/room-bindings/*/balance-refresh', route => {
    keys.push(route.request().headers()['idempotency-key'])
    if (keys.length === 1) return route.fulfill({ status: 429, headers: { 'Retry-After': '60' },
      json: { error: { code: 'RATE_LIMITED', message: '请求额度暂不可用', retryable: true,
        retry_after_seconds: 60 }, meta: envelope({}).meta } })
    return route.fulfill({ status: 202,
      json: envelope({ operation_id: id, state: 'accepted', poll_url: `/api/v1/operations/${id}` }) })
  })
  await page.route('**/api/v1/operations/' + id, route => route.fulfill({
    json: envelope({ id, type: 'balance_refresh', state: 'succeeded' }) }))
  await page.goto('/details')
  await page.getByRole('button', { name: '刷新学校余额' }).click()
  await expect(page.getByText(/请至少等待 60 秒后用原请求重试/)).toBeVisible()
  await expect(page.getByRole('button', { name: '查询原请求的受理结果' })).toBeDisabled()
  await page.reload()
  await page.getByRole('button', { name: '查询原请求的受理结果' }).click()
  expect(keys).toHaveLength(1)
  await page.clock.fastForward(61000)
  await page.getByRole('button', { name: '查询原请求的受理结果' }).click()
  await expect.poll(() => keys.length).toBe(2)
  expect(keys[0]).toBe(keys[1])
})

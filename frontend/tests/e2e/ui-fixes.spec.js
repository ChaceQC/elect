import { expect, test } from '@playwright/test'
import { visualFixture } from '../fixtures/visual.js'
import { bindings, envelope, me } from '../fixtures/t2.js'
import { capability, order, orderId } from '../fixtures/t6.js'

test('页面停留超过五分钟后余额自动标记过期', async ({ page }) => {
  await page.clock.install()
  await visualFixture(page)
  await page.goto('/details')
  await expect(page.locator('.balance-amount')).toHaveText('¥86.42')
  await expect(page.locator('.consumption-chart canvas')).toBeVisible()
  await expect(page.getByText('余额已过期，请刷新确认', { exact: true })).toHaveCount(0)
  await page.clock.fastForward(301_000)
  await expect(page.getByText('余额已过期，请刷新确认', { exact: true })).toBeVisible()
})

test('操作超过两分钟提示暂停，手动恢复会重新自动查询', async ({ page }) => {
  await page.clock.install()
  await visualFixture(page)
  const id = '0199a10c-0000-7000-8000-000000000099'
  const operation = { id, type: 'bind_room', state: 'unknown' }
  let reads = 0
  await page.route('**/api/v1/room-bindings?*', route => route.fulfill({ json: envelope({ ...bindings, pending_operations: [operation] }) }))
  await page.route('**/api/v1/operations/' + id, route => { reads += 1; return route.fulfill({ json: envelope(operation) }) })
  await page.goto('/rooms')
  await expect(page.getByText('学校绑定：结果尚未确认')).toBeVisible()
  await page.clock.fastForward(121_000)
  await expect(page.getByText(/已暂停自动刷新/)).toBeVisible()
  const pausedReads = reads
  await page.clock.fastForward(30_000)
  expect(reads).toBe(pausedReads)
  await page.getByRole('button', { name: '恢复自动更新' }).click()
  await expect(page.getByText(/已暂停自动刷新/)).toHaveCount(0)
  await expect.poll(() => reads).toBeGreaterThan(pausedReads)
  const refreshed = reads
  await page.clock.fastForward(2100)
  await expect.poll(() => reads).toBeGreaterThan(refreshed)
})

test('支付未开放仍可查看原订单，恢复自动更新不创建新单', async ({ page }) => {
  await page.clock.install()
  await visualFixture(page)
  let reads = 0
  await page.route('**/api/v1/payments/capabilities?*', route => route.fulfill({ json: envelope({ ...capability,
    enabled: false, unavailable_reason: '支付暂未开放', unresolved_order: order }) }))
  await page.route('**/api/v1/payment-orders/' + orderId, route => { reads += 1; return route.fulfill({ json: envelope(order) }) })
  await page.goto('/rooms')
  await page.getByRole('button', { name: '查看原充值订单' }).click()
  await expect(page.getByText('支付状态尚未确认')).toBeVisible()
  await expect(page.getByLabel('充值金额（元）')).toHaveCount(0)
  await page.clock.fastForward(121_000)
  await expect(page.getByText(/已暂停自动刷新/)).toBeVisible()
  const previous = reads
  await page.getByRole('button', { name: '查询支付结果' }).click()
  await expect(page.getByText(/已暂停自动刷新/)).toHaveCount(0)
  await expect.poll(() => reads).toBeGreaterThan(previous)
})

test('绑定总数从十一减为十时自动回到第一页；未开放不进入选房', async ({ page }) => {
  await visualFixture(page)
  let total = 11
  const pages = []
  await page.route('**/api/v1/room-bindings?*', route => {
    const number = Number(new URL(route.request().url()).searchParams.get('page'))
    pages.push(number)
    if (number === 2) total = 10
    const room = { id: me.id, room_id: me.id, building: '合成楼', number: '101', display_name: '合成楼-101', status: 'active', balance: null }
    return route.fulfill({ json: envelope({ ...bindings, sync_status: 'ready', total, page: number,
      binding_write_enabled: false, items: number === 1 ? [room] : [] }) })
  })
  await page.goto('/rooms')
  await expect(page.getByRole('button', { name: '新增绑定', exact: true })).toBeDisabled()
  await expect(page.getByText(/新增和删除学校绑定暂未开放/)).toBeVisible()
  await expect(page.getByRole('button', { name: '充值电费' })).toBeDisabled()
  await expect(page.getByText('支付暂未开放', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.locator('.room-card')).toHaveCount(1)
  await expect.poll(() => pages.includes(2)).toBe(true)
  await expect(page.locator('.count')).toHaveText('10')
  await expect(page.getByRole('button', { name: '下一页' })).toHaveCount(0)
  await expect(page.getByText('第 2 页')).toHaveCount(0)
  await page.goto('/rooms?bind=1')
  await expect(page.getByRole('dialog')).toContainText('新增和删除学校绑定暂未开放')
  await expect(page.getByRole('button', { name: '合成甲楼' })).toHaveCount(0)
})

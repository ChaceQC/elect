import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { bindings, envelope, me } from '../fixtures/t2.js'
import { monitor } from '../fixtures/t3.js'

const oldId = '0199a10c-0000-7000-8000-000000000003'
const newId = '0199a10c-0000-7000-8000-000000000004'
const bindId = '0199a10c-0000-7000-8000-000000000009'
const defaultId = '0199a10c-0000-7000-8000-000000000010'
/** @param {string} id @param {string} name */
const room = (id, name) => ({ id, room_id: id, display_name: name, building: name.split('-')[0],
  number: name.split('-')[1], status: 'active', balance: null })
/** @param {import('@playwright/test').Page} page @param {string} name */
async function capture(page, name) {
  const directory = process.env.ELECT_T3_SCREENSHOT_DIR
  if (!directory) return
  await mkdir(directory, { recursive: true })
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true })
}

for (const width of [1440, 375]) {
  test(`${width}px：筛选和列表内搜索、绑定未知刷新恢复、独立查看与默认终态`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let state = '', defaultState = '', bindCount = 0, defaultCount = 0, filterCount = 0
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      const done = state === 'succeeded', switched = defaultState === 'succeeded'
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings' && request.method() === 'POST') {
        bindCount += 1; state = 'unknown'
        expect(request.postDataJSON()).toEqual({ candidate_id: 'synthetic-candidate' })
        return route.fulfill({ status: 202, json: envelope({ operation_id: bindId, state: 'accepted', poll_url: `/api/v1/operations/${bindId}` }) })
      }
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope({ ...bindings,
        items: done ? [room(oldId, '合成原楼-301'), room(newId, '枫苑5号-402')] : [room(oldId, '合成原楼-301')],
        total: done ? 2 : 1, default_binding_id: switched ? newId : oldId, preference_version: switched ? 2 : 1,
        default_switch_operation_id: defaultState === 'running' ? defaultId : null,
        pending_operations: [state === 'unknown' ? { id: bindId, type: 'bind_room', state, target_binding_id: null, created_at: bindings.last_synced_at } : null,
          defaultState === 'running' ? { id: defaultId, type: 'switch_default', state: 'running', target_binding_id: newId, created_at: bindings.last_synced_at } : null].filter(Boolean) }) })
      if (path === '/api/v1/room-candidates/buildings') { filterCount += 1; return route.fulfill({ json: envelope({ items: [{ id: 'b5', label: '枫苑5号' }, { id: 'b6', label: '其他楼栋' }] }) }) }
      if (path === '/api/v1/room-candidates/floors') { filterCount += 1; return route.fulfill({ json: envelope({ items: [{ id: '4', label: '4层' }] }) }) }
      if (path === '/api/v1/room-candidates/rooms') { filterCount += 1; return route.fulfill({ json: envelope({ items: [{ id: 'r402', label: '402' }, { id: 'r403', label: '403' }] }) }) }
      if (path === '/api/v1/room-candidates') {
        expect(new URL(request.url()).searchParams.get('room_id')).toBe('r402')
        return route.fulfill({ json: envelope({ items: [{ candidate_id: 'synthetic-candidate', room_id: 'r402', building: '枫苑5号', number: '402',
          display_name: '枫苑5号-402', already_bound: false, expires_at: new Date(Date.now() + 300_000).toISOString() }],
          page: 1, page_size: 10, total: 1, search_quality: 'exact', expires_at: new Date(Date.now() + 300_000).toISOString() }) })
      }
      if (path === `/api/v1/operations/${bindId}`) return route.fulfill({ json: envelope({ id: bindId, type: 'bind_room', state,
        binding_status: done ? 'confirmed' : 'unknown', default_status: done ? 'unchanged' : 'pending', error_code: null }) })
      if (path === '/api/v1/room-preferences/default') {
        defaultCount += 1; defaultState = 'running'
        expect(request.postDataJSON()).toEqual({ binding_id: newId, expected_version: 1 })
        return route.fulfill({ status: 202, json: envelope({ operation_id: defaultId, state: 'accepted', poll_url: `/api/v1/operations/${defaultId}` }) })
      }
      if (path === `/api/v1/operations/${defaultId}`) return route.fulfill({ json: envelope({ id: defaultId, type: 'switch_default', state: defaultState,
        binding_status: null, default_status: switched ? 'confirmed' : 'switching', error_code: null }) })
      if (path === `/api/v1/room-bindings/${newId}`) return route.fulfill({ json: envelope(room(newId, '枫苑5号-402')) })
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND' } } })
    })
    await page.goto('/rooms')
    await page.getByRole('button', { name: '新增绑定' }).click()
    await page.getByLabel('搜索当前楼栋列表').fill('枫苑5')
    await expect(page.getByRole('button', { name: '其他楼栋', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: '枫苑5号', exact: true }).click()
    await page.getByRole('button', { name: '4层', exact: true }).click()
    await expect(page.getByRole('button', { name: '403', exact: true })).toBeVisible()
    await page.getByLabel('搜索当前房间列表').fill('402')
    await expect(page.getByRole('button', { name: '403', exact: true })).toHaveCount(0)
    expect(filterCount).toBe(3)
    await page.getByRole('button', { name: '402', exact: true }).click()
    await expect(page.getByRole('button', { name: '绑定该寝室' })).toBeVisible()
    await capture(page, `${width}-picker`)
    await page.getByRole('button', { name: '绑定该寝室' }).click()
    await expect(page.getByRole('dialog')).toContainText('枫苑5号-402')
    await page.getByRole('button', { name: '确认绑定', exact: true }).click()
    await expect(page.getByText('学校绑定：结果尚未确认')).toBeVisible()
    await page.reload()
    await expect(page.getByText('学校绑定：结果尚未确认')).toBeVisible()
    expect(bindCount).toBe(1)
    state = 'succeeded'
    await page.getByRole('button', { name: '查询最新进度' }).click()
    await expect(page.locator('.room-card').filter({ hasText: '枫苑5号-402' })).toBeVisible()
    await page.locator('.room-card').filter({ hasText: '枫苑5号-402' }).getByRole('link', { name: '查看寝室' }).click()
    await expect(page.getByText('查看此寝室不会修改默认寝室或监控目标。')).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { name: '枫苑5号-402' })).toBeVisible()
    expect(defaultCount).toBe(0)
    await page.getByRole('link', { name: '返回我的寝室' }).click()
    const newCard = page.locator('.room-card').filter({ hasText: '枫苑5号-402' })
    const oldCard = page.locator('.room-card').filter({ hasText: '合成原楼-301' })
    await newCard.getByRole('button', { name: '设为默认' }).click()
    expect(defaultCount).toBe(0)
    await expect(page.getByText(/之后采集和提醒均以该寝室为目标/)).toBeVisible()
    await page.getByRole('button', { name: '确认切换', exact: true }).click()
    await expect(page.getByText('默认切换：处理中')).toBeVisible()
    await expect(oldCard).toContainText('默认寝室')
    await expect(newCard).not.toContainText('默认寝室')
    await page.reload()
    await expect(page.getByText('默认切换：处理中')).toBeVisible()
    defaultState = 'succeeded'
    await page.getByRole('button', { name: '查询最新进度' }).click()
    await expect(newCard).toContainText('默认寝室')
    expect(defaultCount).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await capture(page, `${width}-rooms`)
  })

  test(`${width}px：异常草稿仍可关闭、冲突核对和路由草稿保留`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let saved = monitor(), conflict = true
    const writes = /** @type {Record<string,unknown>[]} */ ([])
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/v1/auth/me') return route.fulfill({ json: envelope(me) })
      if (path === '/api/v1/room-bindings') return route.fulfill({ json: envelope(bindings) })
      if (path === '/api/v1/monitor' && route.request().method() === 'PATCH') {
        const body = route.request().postDataJSON(); writes.push(body)
        if (Object.keys(body).length === 2) saved = { ...saved, version: 2, state: 'disabled', config: { ...saved.config, enabled: false } }
        else if (conflict) {
          conflict = false; saved = { ...saved, version: 3, config: { ...saved.config, interval_minutes: 1440 } }
          return route.fulfill({ status: 409, json: { error: { code: 'VERSION_CONFLICT' } } })
        } else saved = { ...saved, version: 4, config: { ...saved.config, interval_minutes: body.interval_minutes, email: body.email } }
        return route.fulfill({ json: envelope(saved) })
      }
      if (path === '/api/v1/monitor') return route.fulfill({ json: envelope(saved) })
      return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND' } } })
    })
    await page.goto('/monitor')
    await page.getByLabel('采集间隔（整数分钟）').fill('60.5')
    await page.getByLabel('提醒邮箱', { exact: true }).fill('invalid')
    await page.getByLabel('启用监控').uncheck()
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await expect(page.getByText('监控已关闭。其他修改请另行保存。')).toBeVisible()
    expect(writes[0]).toEqual({ enabled: false, expected_version: 1 })
    await page.getByRole('link', { name: '选择与绑定', exact: true }).click()
    await page.getByRole('link', { name: '监控与预警', exact: true }).click()
    await expect(page.getByLabel('采集间隔（整数分钟）')).toHaveValue('60.5')
    await page.getByLabel('采集间隔（整数分钟）').fill('75')
    await page.getByLabel('提醒邮箱', { exact: true }).fill('synthetic@example.invalid')
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await expect(page.getByText('请核对最新保存的设置')).toBeVisible()
    await expect(page.getByRole('heading', { name: '已保存设置' })).toBeVisible()
    await expect(page.getByLabel('采集间隔（整数分钟）')).toHaveValue('75')
    await page.getByRole('button', { name: '按最新设置继续保存草稿' }).click()
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await expect(page.getByText('监控设置已保存。')).toBeVisible()
    expect(writes.at(-1)?.expected_version).toBe(3)
    expect(writes.at(-1)?.interval_minutes).toBe(75)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await capture(page, `${width}-monitor`)
  })
}

// 显式指定目标的真实新增验收；禁止截图/trace/输出原始认证和学校记录。
import { writeFile } from 'node:fs/promises'
import { chromium, expect } from '@playwright/test'
import { schoolLogin, readApp } from './live-school-helpers.mjs'

const args = process.argv.slice(2)
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : null
const authFile = option('--auth-file'), target = option('--target'), recordFile = option('--record')
if (!authFile || target !== '枫苑5号-402') throw new Error('必须显式提供凭据文件和已授权目标枫苑5号-402')
const record = { date: new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()),
  source: '生产前端 + 正式后端 + 真实学校', target, real_binding_write: false,
  real_smtp: false, payment_writes: false, production_bind_requests: 0 }
const browser = await chromium.launch({ executablePath: process.env.ELECT_BROWSER_PATH ?? '/usr/bin/chromium',
  args: ['--host-resolver-rules=MAP elect.test.local:443 127.0.0.1:18443'] })
try {
  const page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } })
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/v1/room-bindings' && request.method() === 'POST') record.production_bind_requests += 1
  })
  const auth = await schoolLogin(page, authFile, record)
  record.stage = 'binding_sync'
  let before
  await expect.poll(async () => {
    const response = await readApp(page, '/room-bindings')
    before = response.data
    return response.ok && before.sync_status === 'ready' && !before.default_switch_operation_id
  }, { timeout: 90_000, intervals: [1000, 2000] }).toBe(true)
  record.bound_room_count_before = before.total
  record.stage = 'hierarchy_picker'
  const buildings = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-candidates/buildings')
  await page.getByRole('button', { name: '选择寝室' }).click()
  const buildingResponse = await buildings
  if (!buildingResponse.ok()) throw new Error('BUILDINGS_FAILED')
  const matches = (await buildingResponse.json()).data.items.filter(item => item.label === '枫苑5号')
  if (matches.length !== 1) throw new Error('BUILDING_NOT_UNIQUE')
  await page.getByLabel('搜索当前楼栋列表').fill('枫苑5号')
  const floors = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-candidates/floors')
  await page.getByRole('button', { name: '枫苑5号', exact: true }).click()
  const floorResponse = await floors
  if (!floorResponse.ok()) throw new Error('FLOORS_FAILED')
  const fourth = (await floorResponse.json()).data.items.filter(item => item.id === '4')
  if (fourth.length !== 1) throw new Error('FLOOR_NOT_UNIQUE')
  const rooms = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-candidates/rooms')
  await page.getByRole('button', { name: fourth[0].label, exact: true }).click()
  const roomResponse = await rooms
  if (!roomResponse.ok()) throw new Error('ROOMS_FAILED')
  const chosen = (await roomResponse.json()).data.items.filter(item => item.label === '402' || item.label.endsWith('-402'))
  if (chosen.length !== 1) throw new Error('ROOM_NOT_UNIQUE')
  await page.getByLabel('搜索当前房间列表').fill('402')
  const checked = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-candidates')
  await page.getByRole('button', { name: chosen[0].label, exact: true }).click()
  const candidateResponse = await checked
  if (!candidateResponse.ok()) throw new Error('CANDIDATE_FAILED')
  const value = (await candidateResponse.json()).data
  if (value.items.length !== 1 || value.items[0].room_id !== chosen[0].id ||
      value.items[0].building !== '枫苑5号' || value.items[0].number !== '402') throw new Error('TARGET_MISMATCH')
  record.filtered_target_verified = true
  let resultBinding
  if (!value.items[0].already_bound) {
    record.stage = 'bind_acceptance'
    await page.getByRole('button', { name: '绑定该寝室' }).click()
    await expect(page.getByRole('dialog')).toContainText('枫苑5号')
    const accepted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-bindings' && response.request().method() === 'POST')
    await page.getByRole('button', { name: '确认绑定', exact: true }).click()
    const response = await accepted
    if (response.status() !== 202) { record.failure_code = (await response.json()).error?.code; throw new Error('BIND_NOT_ACCEPTED') }
    const operation = (await response.json()).data.operation_id
    record.binding_operation_id = operation
    record.stage = 'B02_confirmation'
    let status
    await expect.poll(async () => {
      status = (await readApp(page, `/operations/${operation}`)).data
      return ['succeeded', 'failed', 'unknown'].includes(status.state)
    }, { timeout: 120_000, intervals: [1000, 2000, 5000] }).toBe(true)
    if (status.state !== 'succeeded' || status.binding_status !== 'confirmed') {
      record.binding_state = status.state; record.failure_code = status.error_code; throw new Error('BIND_UNCONFIRMED')
    }
    if (record.production_bind_requests !== 1) throw new Error('MULTIPLE_BIND_REQUESTS')
    resultBinding = status.result_binding_id
    record.binding_state = status.state; record.default_status = status.default_status
    record.real_binding_write = true
  } else record.previously_bound = true
  const after = (await readApp(page, '/room-bindings')).data
  if (before.default_binding_id && after.default_binding_id !== before.default_binding_id) throw new Error('EXISTING_DEFAULT_CHANGED')
  record.existing_default_preserved = true
  record.bound_room_count_after = after.total
  await page.reload()
  await expect(page.locator('.room-card').filter({ hasText: '枫苑5号 402' })).toBeVisible({ timeout: 30_000 })
  record.refresh_restore = 'passed'
  if (resultBinding) {
    await page.locator('.room-card').filter({ hasText: '枫苑5号 402' }).getByRole('link', { name: '查看寝室' }).click()
    await expect(page.getByText('查看此寝室不会修改默认寝室或监控目标。')).toBeVisible()
    record.independent_view = 'passed'
  }
  await page.setViewportSize({ width: 375, height: 900 })
  await page.getByRole('link', { name: '监控提醒', exact: true }).click()
  await expect(page.getByRole('heading', { name: '监控提醒' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '已保存设置' })).toBeVisible({ timeout: 30_000 })
  if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('MOBILE_OVERFLOW')
  record.mobile_monitor_read = 'passed'
  const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))
  if (storage.includes(auth.password) || storage.includes(auth.student)) throw new Error('SENSITIVE_STORAGE')
  record.sensitive_browser_storage = false
  await page.getByRole('button', { name: '我的账户' }).click()
  await page.getByRole('button', { name: '退出应用', exact: true }).click()
  await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  record.application_logout = 'passed'
  record.result = 'passed'; delete record.stage
} catch (error) { record.result = 'failed'; record.failure_class = error.name }
finally { await browser.close() }
if (recordFile) await writeFile(recordFile, JSON.stringify(record, null, 2) + '\n')
console.log(JSON.stringify(record, null, 2))
if (record.result !== 'passed') process.exitCode = 1

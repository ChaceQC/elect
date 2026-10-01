// 用户明确指定的真实删除验收；不截图/trace，不输出学校身份或认证材料。
import { writeFile } from 'node:fs/promises'
import { chromium, expect } from '@playwright/test'
import { schoolLogin, readApp } from './live-school-helpers.mjs'

const args = process.argv.slice(2)
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : null
const authFile = option('--auth-file'), target = option('--target'), recordFile = option('--record')
if (!authFile || target !== '枫苑5号-402') throw new Error('必须显式提供凭据文件与已授权删除目标枫苑5号-402')
const record = { date: new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()),
  source: '生产前端 + 正式后端 + 真实学校', target, real_smtp: false, payment_writes: false,
  production_delete_requests: 0, real_binding_removal: false }
const browser = await chromium.launch({ executablePath: process.env.ELECT_BROWSER_PATH ?? '/usr/bin/chromium',
  args: ['--host-resolver-rules=MAP elect.test.local:443 127.0.0.1:18443'] })
try {
  const page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } })
  page.on('request', request => {
    if (/^\/api\/v1\/room-bindings\/[^/]+$/.test(new URL(request.url()).pathname) && request.method() === 'DELETE') record.production_delete_requests += 1
  })
  const auth = await schoolLogin(page, authFile, record)
  record.stage = 'select_owned_target'
  const before = (await readApp(page, '/room-bindings')).data
  const matches = before.items.filter(item => item.building === '枫苑5号' && item.number === '402' && item.status === 'active')
  if (matches.length !== 1) throw new Error('DELETE_TARGET_NOT_UNIQUE')
  const chosen = matches[0]
  await page.locator('.room-card').filter({ hasText: chosen.display_name }).getByRole('button', { name: '删除绑定', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText(chosen.display_name)
  await page.getByLabel('我确认解除该寝室的学校绑定').check()
  record.stage = 'delete_acceptance'
  const accepted = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/room-bindings/${chosen.id}` && response.request().method() === 'DELETE')
  await page.getByRole('button', { name: '确认删除绑定', exact: true }).click()
  const response = await accepted
  if (response.status() !== 202) { record.failure_code = (await response.json()).error?.code; throw new Error('DELETE_NOT_ACCEPTED') }
  const operation = (await response.json()).data.operation_id
  record.removal_operation_id = operation
  record.stage = 'B02_repeated_absence'
  let status
  await expect.poll(async () => {
    status = (await readApp(page, `/operations/${operation}`)).data
    return ['succeeded', 'failed', 'unknown'].includes(status.state)
  }, { timeout: 150_000, intervals: [1000, 2000, 5000] }).toBe(true)
  if (status.state !== 'succeeded' || status.binding_status !== 'removed') {
    record.removal_state = status.state; record.failure_code = status.error_code; throw new Error('REMOVAL_UNCONFIRMED')
  }
  if (record.production_delete_requests !== 1) throw new Error('MULTIPLE_DELETE_REQUESTS')
  const after = (await readApp(page, '/room-bindings')).data
  if (after.items.some(item => item.id === chosen.id)) throw new Error('REMOVED_TARGET_VISIBLE')
  if (before.default_binding_id !== chosen.id && before.default_binding_id !== after.default_binding_id) throw new Error('EXISTING_DEFAULT_CHANGED')
  record.real_binding_removal = true
  record.binding_status = status.binding_status; record.default_status = status.default_status
  record.bound_room_count_before = before.total; record.bound_room_count_after = after.total
  record.existing_default_preserved = before.default_binding_id !== chosen.id && before.default_binding_id === after.default_binding_id
  await page.reload()
  await expect(page.locator('.room-card').filter({ hasText: chosen.display_name })).toHaveCount(0)
  record.refresh_restore = 'passed'
  await page.goto(`https://elect.test.local/rooms/${chosen.id}`)
  await expect(page).toHaveURL('https://elect.test.local/rooms')
  await expect(page.getByText('所查看的寝室已不可用，已返回本人列表')).toBeVisible()
  record.removed_view_404_recovery = 'passed'
  await page.setViewportSize({ width: 375, height: 900 })
  if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('MOBILE_OVERFLOW')
  record.mobile_list = 'passed'
  const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))
  if (storage.includes(auth.password) || storage.includes(auth.student)) throw new Error('SENSITIVE_STORAGE')
  record.sensitive_browser_storage = false
  await page.getByRole('button', { name: '我的账户' }).click()
  await page.getByRole('button', { name: '退出应用', exact: true }).click()
  await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  record.application_logout = 'passed'; record.result = 'passed'; delete record.stage
} catch (error) { record.result = 'failed'; record.failure_class = error.name }
finally { await browser.close() }
if (recordFile) await writeFile(recordFile, JSON.stringify(record, null, 2) + '\n')
console.log(JSON.stringify(record, null, 2))
if (record.result !== 'passed') process.exitCode = 1

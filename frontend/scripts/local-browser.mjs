// 本机部署的真实学校只读浏览器检查；凭据/页面/验证码不输出或截图。
import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { chromium, expect } from '@playwright/test'
import { readAuth } from './live-school-helpers.mjs'

const origin = process.env.ELECT_BROWSER_ORIGIN
assert(origin?.startsWith('http://'))
const record = { source: '本机HTTP/Nginx/正式后端/真实学校只读', result: 'running' }
const browser = await chromium.launch({ headless: true })
let context
let csrf
try {
  context = await browser.newContext({ baseURL: origin, viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', () => errors.push('pageerror'))
  record.stage = 'captcha'
  await page.goto('/rooms')
  await expect(page.getByAltText('学校算式验证码')).toBeVisible({ timeout: 40_000 })
  const image = await page.getByAltText('学校算式验证码').getAttribute('src')
  await writeFile('/run/check/captcha.json', JSON.stringify({ image }), { mode: 0o600 })
  let answer = ''
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try { answer = (await readFile('/run/check/answer.txt', 'utf8')).trim() } catch { /* 等待离线OCR容器。 */ }
    if (answer) break
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  assert(answer, 'CAPTCHA_NOT_SOLVED')
  record.stage = 'login'
  const auth = await readAuth('/run/auth.txt')
  await page.getByLabel('学校账号', { exact: true }).fill(auth.student)
  await page.getByLabel('学校密码').fill(auth.password)
  await page.getByLabel('验证码答案').fill(answer)
  await page.getByRole('button', { name: '阅读应用协议' }).click()
  await page.locator('.agreement-content').evaluate(element => { element.scrollTop = element.scrollHeight })
  await page.getByRole('button', { name: '我已阅读' }).click()
  await page.getByLabel('我同意应用使用协议').check()
  await page.getByLabel('允许后台使用加密凭据恢复学校认证').check()
  const authenticated = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/auth/login', { timeout: 75_000 })
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const login = await authenticated
  if (!login.ok()) { record.failure_code = (await login.json()).error?.code; throw new Error('LOGIN_FAILED') }
  await expect(page.getByRole('heading', { name: '我的寝室', exact: true })).toBeVisible({ timeout: 75_000 })
  record.authentication = 'passed'
  const cookies = await context.cookies()
  assert(cookies.some(cookie => cookie.name === 'elect_session_local' && !cookie.secure && cookie.httpOnly))
  const me = await context.request.get('/api/v1/auth/me')
  assert(me.status() === 200)
  const user = (await me.json()).data
  csrf = user.csrf_token
  assert((await context.request.post('/api/v1/auth/logout', { headers: {
    Origin: 'http://other.invalid', 'X-CSRF-Token': csrf,
  } })).status() === 403)
  assert((await context.request.post('/api/v1/auth/logout', { headers: { Origin: origin } })).status() === 403)
  record.origin_csrf = 'passed'
  record.stage = 'binding_and_capabilities'
  await expect(page.locator('.room-card').first()).toBeVisible({ timeout: 70_000 })
  const bindings = await context.request.get('/api/v1/room-bindings')
  assert(bindings.ok())
  const beforeSync = (await bindings.json()).data
  let binding = beforeSync.items[0]
  assert(binding?.id)
  record.school_binding_read = 'passed'
  if (process.env.ELECT_VERIFY_SCHOOL_SYNC === 'true') {
    record.stage = 'school_sync'
    const accepted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-bindings/sync')
    await page.getByRole('button', { name: '同步学校绑定', exact: true }).click()
    const response = await accepted
    assert(response.status() === 202)
    const operationId = (await response.json()).data.operation_id
    let synced
    let operation
    for (let attempt = 0; attempt < 80; attempt += 1) {
      operation = (await (await context.request.get(`/api/v1/operations/${operationId}`)).json()).data
      synced = (await (await context.request.get('/api/v1/room-bindings?page_size=100')).json()).data
      if (operation.state === 'succeeded' && !synced.default_switch_operation_id) break
      assert(operation.state !== 'failed')
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    assert(operation.state === 'succeeded' && !synced.default_switch_operation_id)
    assert(synced.sync_status === 'ready' && synced.total === synced.items.length)
    assert(synced.items.every(item => item.status === 'active'))
    if (synced.items.some(item => item.id === beforeSync.default_binding_id)) {
      assert(synced.default_binding_id === beforeSync.default_binding_id)
      record.default_policy = 'preserved'
    } else {
      assert(synced.default_binding_id === operation.target_binding_id)
      record.default_policy = 'school_first'
    }
    record.authoritative_school_sync = 'passed'
    record.synced_rooms = synced.total
    binding = synced.items.find(item => item.id === synced.default_binding_id)
    record.stage = 'balance_refresh'
    await page.goto(`/rooms/${binding.id}`)
    const refreshed = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/balance-refresh'))
    await page.getByRole('button', { name: '刷新学校余额', exact: true }).click()
    const refresh = await refreshed
    assert(refresh.status() === 202)
    const refreshId = (await refresh.json()).data.operation_id
    let completed
    for (let attempt = 0; attempt < 80; attempt += 1) {
      completed = (await (await context.request.get(`/api/v1/operations/${refreshId}`)).json()).data
      if (completed.state === 'succeeded') break
      assert(completed.state !== 'failed')
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    assert(completed.state === 'succeeded')
    const balance = (await (await context.request.get(`/api/v1/room-bindings/${binding.id}/balance`)).json()).data
    assert(typeof balance.amount === 'string' && !balance.stale && balance.fetched_at)
    record.manual_balance_refresh = 'passed'
  }
  const payments = await context.request.get(`/api/v1/payments/capabilities?binding_id=${binding.id}`)
  assert(payments.ok() && !(await payments.json()).data.enabled)
  record.payment_closed = true
  record.stage = 'readonly_pages'
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 })
    for (const [path, title] of [['overview', '用电总览'], ['details', '电费明细'], ['rooms', '我的寝室'], ['monitor', '监控提醒']]) {
      assert((await page.goto(`/${path}`)).status() === 200)
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    }
  }
  record.page_reads = 8
  await page.goto('/rooms')
  await expect(page.locator('.room-card').first()).toBeVisible({ timeout: 70_000 })
  record.school_binding_read = 'passed'
  await page.reload()
  await expect(page.locator('.room-card').first()).toBeVisible()
  record.session_restore = 'passed'
  record.stage = 'local_retry_stop'
  let bindingWrites = 0
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/room-bindings') bindingWrites += 1
  })
  await page.evaluate(userId => {
    const key = '6e6024bb-a63b-4fa0-8d5b-6a7e8bcd5e91'
    sessionStorage.setItem(`elect.intent.${userId}.${key}`, JSON.stringify({
      key, path: '/room-bindings', body: { candidate_id: 'synthetic-local-retry-only' },
      kind: 'operation', method: 'POST', id: null, createdAt: Date.now(),
    }))
  }, user.id)
  await page.reload()
  await expect(page.getByText('有一笔学校绑定受理尚未确认')).toBeVisible()
  await page.getByRole('button', { name: '停止本地重试' }).click()
  await expect(page.getByText('已停止本地重试；学校请求仍可能已受理，请同步学校绑定核对。')).toBeVisible()
  assert(bindingWrites === 0)
  record.local_retry_stop = 'passed'
  record.school_write_requests = bindingWrites
  const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))
  assert(!storage.includes(auth.password) && !storage.includes(auth.student))
  record.sensitive_browser_storage = false
  const other = await context.newPage()
  await other.goto('/rooms')
  await expect(other.getByRole('button', { name: '我的账户' })).toBeVisible()
  await page.getByRole('button', { name: '我的账户' }).click()
  await page.getByRole('button', { name: '退出应用', exact: true }).click()
  await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  await expect(other.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  assert((await context.request.get('/api/v1/auth/me')).status() === 401)
  assert(errors.length === 0)
  record.cross_tab_logout = 'passed'
  record.page_errors = errors.length
  record.result = 'passed'
  delete record.stage
} catch (error) {
  record.result = 'failed'
  record.failure_class = error.name
} finally {
  if (record.result === 'failed' && context && csrf) {
    await context.request.post('/api/v1/auth/logout', { headers: {
      Origin: origin, 'X-CSRF-Token': csrf,
    } }).catch(() => {})
  }
  await browser.close()
}
console.log(JSON.stringify(record))
if (record.result !== 'passed') process.exitCode = 1

// 正式生产前端/后端的本人只读联调；不记录认证材料、学校IDs、金额或真实截图。
import { writeFile } from 'node:fs/promises'
import { chromium, expect } from '@playwright/test'
import { schoolLogin, readApp } from './live-school-helpers.mjs'

const args = process.argv.slice(2)
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : null
const authFile = option('--auth-file'), output = option('--record')
if (!authFile) throw new Error('必须显式提供本地凭据文件')
const record = /** @type {Record<string,any>} */ ({ date: new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()), source: '生产前端 + 正式后端 + 真实学校本人只读', school_binding_writes: false, payment_writes: false, real_smtp: false })
const browser = await chromium.launch({ executablePath: process.env.ELECT_BROWSER_PATH ?? '/usr/bin/chromium',
  args: ['--host-resolver-rules=MAP elect.test.local:443 127.0.0.1:18443'] })
let page = /** @type {import('@playwright/test').Page|null} */ (null)
let saved = /** @type {import('../src/api/generated').components['schemas']['Monitor']|null} */ (null)
/** @param {string} path @param {string} method @param {unknown} body */
async function writeApp(path, method, body) {
  if (!page) throw new Error('NO_PAGE')
  return page.evaluate(async ({ path, method, body }) => {
    const me = await (await fetch('/api/v1/auth/me')).json()
    const response = await fetch(`/api/v1${path}`, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': me.data.csrf_token }, body: JSON.stringify(body) })
    return { ok: response.ok, ...(await response.json()) }
  }, { path, method, body })
}
try {
  page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } })
  const auth = await schoolLogin(page, authFile, record)
  await expect.poll(async () => (await readApp(page, '/room-bindings')).data.default_binding_id, { timeout: 60_000, intervals: [1000, 2000] }).toBeTruthy()
  const bindings = (await readApp(page, '/room-bindings')).data
  const binding = bindings.default_binding_id
  record.bound_room_count = bindings.total
  await page.goto('https://elect.test.local/overview')
  await expect(page.getByRole('heading', { name: '用电总览' })).toBeVisible()
  record.stage = 'balance_refresh'
  const accepted = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/balance-refresh'))
  await page.getByRole('button', { name: '刷新学校余额', exact: true }).click()
  const refresh = await accepted
  if (refresh.status() !== 202) throw new Error('BALANCE_NOT_ACCEPTED')
  const refreshId = (await refresh.json()).data.operation_id
  await expect.poll(async () => (await readApp(page, `/operations/${refreshId}`)).data.state, { timeout: 60_000, intervals: [1000, 2000, 5000] }).toBe('succeeded')
  const balance = (await readApp(page, `/room-bindings/${binding}/balance`)).data
  if (balance.amount === null || balance.stale || !balance.fetched_at) throw new Error('BALANCE_NOT_FRESH')
  record.real_B02_refresh = 'passed'
  record.stage = 'C02_history'
  await page.goto(`https://elect.test.local/details?binding_id=${binding}`)
  await page.getByRole('button', { name: '最近7天', exact: true }).click()
  await page.getByRole('button', { name: '应用日期范围', exact: true }).click()
  const historyAccepted = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/history-sync'))
  await page.getByRole('button', { name: '同步所选范围的学校历史', exact: true }).click()
  const historyResponse = await historyAccepted
  if (historyResponse.status() !== 202) throw new Error('HISTORY_NOT_ACCEPTED')
  const historyId = (await historyResponse.json()).data.operation_id
  await expect.poll(async () => (await readApp(page, `/operations/${historyId}`)).data.state, { timeout: 120_000, intervals: [2000, 5000, 10000] }).toBe('succeeded')
  const start = await page.getByLabel('开始日期').inputValue(), end = await page.getByLabel('结束日期').inputValue()
  const history = (await readApp(page, `/room-bindings/${binding}/consumption?start_date=${start}&end_date=${end}`)).data
  if (history.start_date !== start || history.end_date !== end || history.summary.complete) throw new Error('HISTORY_COVERAGE_OR_RANGE')
  record.real_C02_sync = 'passed'; record.known_history_days = history.summary.known_days
  record.coverage = history.coverage; record.complete_claimed = history.summary.complete
  await page.reload()
  await expect(page.getByRole('heading', { name: '电费明细' })).toBeVisible()
  await page.setViewportSize({ width: 375, height: 900 })
  if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('MOBILE_OVERFLOW')
  record.mobile_history = 'passed'
  record.stage = 'real_balance_only_run'
  saved = (await readApp(page, '/monitor')).data
  const activated = await writeApp('/monitor', 'PATCH', { ...saved.config, enabled: true, email: saved.config.email ?? 't4-test@example.invalid', expected_version: saved.version })
  if (!activated.ok) throw new Error('MONITOR_NOT_ACTIVATED')
  await page.goto('https://elect.test.local/monitor')
  // 首次启用会由持久Scheduler立即采集；等待真实运行终态。
  let current
  await expect.poll(async () => {
    current = (await readApp(page, '/monitor')).data
    return current.last_run?.state === 'succeeded' && current.last_success_at
  }, { timeout: 120_000, intervals: [1000, 2000, 5000] }).toBeTruthy()
  const samples = (await readApp(page, `/room-bindings/${binding}/monitor-samples?start_date=${end}&end_date=${end}`)).data
  if (!samples.items.some(item => item.run_id === current.last_run.id && item.quality === 'balance_only')) throw new Error('RUN_SAMPLE_MISSING')
  record.real_scheduler_worker_sample = 'passed'; record.sample_count = samples.total
  record.real_sample_snapshot = 'passed'
  const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))
  if (storage.includes(auth.password) || storage.includes(auth.student)) throw new Error('SENSITIVE_STORAGE')
  record.sensitive_browser_storage = false
  record.result = 'passed'; delete record.stage
} catch (error) { record.result = 'failed'; record.failure_class = error.name }
finally {
  if (saved && page) {
    try {
      const latest = (await readApp(page, '/monitor')).data
      const restored = await writeApp('/monitor', 'PATCH', { ...saved.config, expected_version: latest.version })
      record.original_monitor_config_restored = restored.ok
      if (!restored.ok) record.result = 'failed'
    } catch { record.original_monitor_config_restored = false; record.result = 'failed' }
  }
  if (record.result === 'passed' && page) {
    try {
      await page.getByRole('button', { name: '我的账户', exact: true }).click()
      await page.getByRole('button', { name: '退出应用', exact: true }).click()
      await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
      record.application_logout = 'passed'
    } catch { record.result = 'failed'; record.application_logout = 'failed' }
  }
  await browser.close()
}
if (output) await writeFile(output, JSON.stringify(record, null, 2) + '\n')
console.log(JSON.stringify(record, null, 2))
if (record.result !== 'passed') process.exitCode = 1

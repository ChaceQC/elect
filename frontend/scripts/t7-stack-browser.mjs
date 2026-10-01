import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { chromium } from '@playwright/test'

const session = JSON.parse(await readFile('/run/session.json', 'utf8'))
assert(typeof session.cookie === 'string' && session.cookie.length > 20)
const browser = await chromium.launch({ headless: true })
try {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: 'https://elect.test.local' })
  await context.addCookies([{ name: '__Host-elect_session', value: session.cookie,
    domain: 'elect.test.local', path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }])
  const page = await context.newPage()
  const failures = []
  page.on('pageerror', () => failures.push('pageerror'))
  const api = context.request
  const me = await api.get('/api/v1/auth/me')
  assert(me.status() === 200)
  const csrf = (await me.json()).data.csrf_token
  const forbidden = await api.post('/api/v1/auth/logout', { headers: {
    Origin: 'https://other.invalid', 'X-CSRF-Token': csrf } })
  assert(forbidden.status() === 403)
  const wrongCsrf = await api.post('/api/v1/auth/logout', { headers: {
    Origin: 'https://elect.test.local', 'X-CSRF-Token': 'wrong' } })
  assert(wrongCsrf.status() === 403)
  const foreign = await api.get(`/api/v1/room-bindings/${session.foreign_binding}`)
  assert(foreign.status() === 404)
  const pages = [['overview', '用电总览'], ['details', '电费明细'], ['rooms', '我的寝室'], ['monitor', '监控提醒']]
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 })
    for (const [path, title] of pages) {
      const response = await page.goto(`/${path}`)
      assert(response.status() === 200)
      await page.getByRole('heading', { name: title, exact: true }).waitFor()
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await page.getByRole('button', { name: '我的账户' }).click()
      await page.getByRole('dialog').waitFor()
      await page.keyboard.press('Escape')
    }
  }
  assert((await page.evaluate(() => navigator.serviceWorker.getRegistrations())).length === 0)
  const other = await context.newPage()
  await other.goto('/rooms')
  await other.getByRole('button', { name: '我的账户' }).waitFor()
  await page.getByRole('button', { name: '我的账户' }).click()
  await page.getByRole('button', { name: '退出应用', exact: true }).click()
  await page.getByRole('form', { name: '学校账号登录' }).waitFor()
  await other.getByRole('form', { name: '学校账号登录' }).waitFor()
  assert((await api.get('/api/v1/auth/me')).status() === 401)
  assert(failures.length === 0)
  console.log(JSON.stringify({ scope: '生产静态前端/Nginx/Gateway/七域后端；登录预置使用合成学校',
    page_reads: 8, mock_routes: 0, cross_origin_rejected: true, csrf_rejected: true,
    foreign_binding_rejected: true, cross_tab_logout: true, session_revoked: true,
    page_errors: failures.length }))
  await context.close()
} finally { await browser.close() }

// 显式真实学校验收；认证材料仅在内存，禁止 trace/截图/原始请求输出。
import { readFile, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { chromium, expect } from '@playwright/test'

/** @param {string} path */
async function readAuth(path) {
  const text = (await readFile(path, 'utf8')).replace(/^\uFEFF/, '').trim()
  let values
  try { values = JSON.parse(text) } catch {
    values = {}
    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^\s*(username|account|sdgl_username|账号|学号|password|pwd|sdgl_password|密码)\s*[:=：]\s*(.*?)\s*$/i)
      if (match) values[match[1].toLowerCase()] = match[2]
    }
    if (!Object.keys(values).length) {
      const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
      if (lines.length === 2) values = { username: lines[0], password: lines[1] }
    }
  }
  const student = ['username', 'account', 'sdgl_username', '账号', '学号'].map(key => values[key]).find(value => typeof value === 'string' && value)
  const password = ['password', 'pwd', 'sdgl_password', '密码'].map(key => values[key]).find(value => typeof value === 'string' && value)
  if (!student || !password) throw new Error('AUTH_FILE_INVALID')
  return { student, password }
}

/** @param {string} image */
function solve(image) {
  return new Promise((accept, reject) => {
    const child = spawn(resolve('../backend/.venv/bin/python'), ['-c',
      'import sys; from services.school_adapter.infrastructure.ocr import solve_image; print(solve_image(sys.stdin.read()) or "")'],
    { cwd: resolve('../backend'), stdio: ['pipe', 'pipe', 'pipe'] })
    let output = ''
    child.stdout.on('data', chunk => { output += chunk.toString() })
    child.stderr.on('data', () => {})
    child.on('error', reject)
    child.on('close', code => code === 0 ? accept(output.trim()) : reject(new Error('OCR_FAILED')))
    child.stdin.end(image)
  })
}

const dateParts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date()).map(part => [part.type, part.value]))
const record = { date: `${dateParts.year}-${dateParts.month}-${dateParts.day}`,
  source: '生产前端 + 真实浏览器 + 正式后端 + 真实学校', external_business_writes: false }
const argumentsList = process.argv.slice(2)
const authFile = argumentsList[argumentsList.indexOf('--auth-file') + 1]
const recordFile = argumentsList.includes('--record') ? argumentsList[argumentsList.indexOf('--record') + 1] : null
if (!argumentsList.includes('--auth-file')) throw new Error('需要显式 --auth-file')
const browser = await chromium.launch({ executablePath: process.env.ELECT_BROWSER_PATH ?? '/usr/bin/chromium',
  args: ['--host-resolver-rules=MAP elect.test.local:443 127.0.0.1:18443'] })
try {
  const page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } })
  record.stage = 'login_form'
  await page.goto('https://elect.test.local/rooms')
  await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  await expect(page.getByAltText('学校算式验证码')).toBeVisible({ timeout: 35_000 })
  let answer = ''
  for (let attempt = 0; attempt < 2; attempt += 1) {
    answer = /** @type {string} */ (await solve(/** @type {string} */ (await page.getByAltText('学校算式验证码').getAttribute('src'))))
    if (answer) break
    if (attempt === 0) { await page.getByRole('button', { name: '换一张' }).click(); await expect(page.getByAltText('学校算式验证码')).toBeVisible() }
  }
  if (!answer) throw new Error('CAPTCHA_NOT_SOLVED')
  const auth = await readAuth(authFile)
  await page.getByLabel('学校账号', { exact: true }).fill(auth.student)
  await page.getByLabel('学校密码').fill(auth.password)
  await page.getByLabel('验证码答案').fill(answer)
  await page.getByRole('button', { name: '阅读应用协议' }).click()
  await page.locator('.agreement-content').evaluate(element => { element.scrollTop = element.scrollHeight })
  await page.getByRole('button', { name: '我已阅读' }).click()
  await page.getByLabel('我同意应用使用协议').check()
  await page.getByLabel('允许后台使用加密凭据恢复学校认证').check()
  record.stage = 'school_login'
  const loginResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/auth/login')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const login = await loginResponse
  if (!login.ok()) { record.failure_code = (await login.json()).error?.code; throw new Error('LOGIN_FAILED') }
  await expect(page.getByRole('heading', { name: '我的寝室', exact: true })).toBeVisible({ timeout: 70_000 })
  record.authentication = 'passed'
  await expect(page.getByLabel('学校密码')).toHaveCount(0)
  record.password_state_cleared = true
  record.stage = 'binding_sync'
  const accepted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-bindings/sync')
  await page.getByRole('button', { name: '同步学校绑定', exact: true }).click()
  const operationResponse = await accepted
  if (operationResponse.status() !== 202) throw new Error('SYNC_NOT_ACCEPTED')
  await expect(page.getByRole('button', { name: '同步学校绑定', exact: true })).toBeEnabled({ timeout: 70_000 })
  await expect(page.locator('.room-card').first()).toBeVisible({ timeout: 70_000 })
  record.binding_sync = 'passed'
  record.bound_room_count = await page.locator('.room-card').count()
  record.stage = 'candidate_page'
  const candidates = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/room-candidates')
  await page.getByRole('button', { name: '查询一页' }).click()
  const candidateResponse = await candidates
  if (!candidateResponse.ok()) throw new Error('CANDIDATES_FAILED')
  record.candidate_page = 'passed'
  record.candidate_count = (await candidateResponse.json()).data.items.length
  await page.reload()
  await expect(page.getByRole('heading', { name: '我的寝室', exact: true })).toBeVisible()
  await expect(page.locator('.room-card').first()).toBeVisible()
  record.application_session_restore = 'passed'
  const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))
  if (storage.includes(auth.password) || storage.includes(auth.student)) throw new Error('SENSITIVE_STORAGE')
  record.sensitive_browser_storage = false
  await page.setViewportSize({ width: 375, height: 900 })
  if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('MOBILE_OVERFLOW')
  await page.getByRole('button', { name: '我的账户' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  record.mobile_account = 'passed'
  await page.getByRole('button', { name: '退出应用', exact: true }).click()
  await expect(page.getByRole('form', { name: '学校账号登录' })).toBeVisible()
  record.application_logout = 'passed'
  record.result = 'passed'
  delete record.stage
} catch (error) { record.result = 'failed'; record.failure_class = error.name }
finally { await browser.close() }
if (recordFile) await writeFile(recordFile, JSON.stringify(record, null, 2) + '\n')
console.log(JSON.stringify(record, null, 2))
if (record.result !== 'passed') process.exitCode = 1

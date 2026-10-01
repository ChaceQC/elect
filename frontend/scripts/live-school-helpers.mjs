// 显式真实验收共享入口；认证材料只在内存，不记录原始请求。
import { readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'

/** @param {string} path */
export async function readAuth(path) {
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
export function solve(image) {
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


/** @param {import('@playwright/test').Page} page @param {string} authFile @param {Record<string,unknown>} record */
export async function schoolLogin(page, authFile, record) {
  const { expect } = await import('@playwright/test')
  record.stage = 'authentication'
  await page.goto('https://elect.test.local/rooms')
  await expect(page.getByAltText('学校算式验证码')).toBeVisible({ timeout: 35_000 })
  let answer = ''
  for (let attempt = 0; attempt < 2; attempt += 1) {
    answer = await solve(await page.getByAltText('学校算式验证码').getAttribute('src'))
    if (answer) break
    if (attempt === 0) {
      const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/auth/captcha')
      await page.getByRole('button', { name: '换一张' }).click(); await refreshed
    }
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
  const authenticated = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/auth/login')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const login = await authenticated
  if (!login.ok()) { record.failure_code = (await login.json()).error?.code; throw new Error('LOGIN_FAILED') }
  await expect(page.getByRole('heading', { name: '我的寝室', exact: true })).toBeVisible({ timeout: 70_000 })
  record.authentication = 'passed'
  return auth
}

/** @param {import('@playwright/test').Page} page @param {string} path */
export async function readApp(page, path) {
  return page.evaluate(async path => {
    const response = await fetch(`/api/v1${path}`, { credentials: 'same-origin', cache: 'no-store' })
    return { ok: response.ok, ...(await response.json()) }
  }, path)
}

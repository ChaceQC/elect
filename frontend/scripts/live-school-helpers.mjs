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


import { readFile, rm } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const temp = fileURLToPath(new URL('../src/api/.generated-check.d.ts', import.meta.url))
const target = new URL('../src/api/generated.d.ts', import.meta.url)
try {
  const result = spawnSync('npx', ['--no-install', 'openapi-typescript',
    '../docs/contracts/openapi.yaml', '-o', temp], { stdio: 'inherit' })
  if (result.status !== 0) throw new Error('契约类型生成失败')
  if (await readFile(temp, 'utf8') !== await readFile(target, 'utf8')) {
    throw new Error('前端类型与 OpenAPI 不同步，请执行 npm run contract:generate')
  }
  console.log('前端类型与 OpenAPI 一致')
} finally {
  await rm(temp, { force: true })
}

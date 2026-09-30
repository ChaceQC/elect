import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const output = fileURLToPath(new URL('../../docs/acceptance/frontend/reference/', import.meta.url))
const baseURL = process.env.ELECT_REFERENCE_URL ?? 'http://127.0.0.1:5179/nature.html'
const browser = await chromium.launch({
  executablePath: process.env.ELECT_BROWSER_PATH,
})
const captures = []
await mkdir(output, { recursive: true })
try {
  for (const width of [375, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, locale: 'zh-CN' })
    const page = await context.newPage()
    await page.goto(baseURL)
    await page.evaluate(() => {
      localStorage.setItem('elect-demo:000000000000', JSON.stringify({
        rooms: [{ id: 'fixture-room', building: '合成楼', number: '示例室', balance: 86.42 }],
        defaultId: 'fixture-room',
        settings: { email: 'fixture@example.invalid', threshold: 20, interval: 60, repeats: 2,
          enabled: true, history: true },
      }))
    })
    const capture = async (name) => {
      await page.evaluate(() => document.fonts.ready)
      await page.screenshot({ path: `${output}/${width}-${name}.png`, fullPage: true, animations: 'disabled' })
      captures.push({ width, state: name, file: `${width}-${name}.png` })
    }
    await capture('login')
    await page.getByRole('button', { name: '《用户协议》' }).click()
    await capture('agreement')
    await page.locator('.agreement-content').evaluate(el => {
      el.scrollTop = el.scrollHeight
      el.dispatchEvent(new Event('scroll', { bubbles: true }))
    })
    await page.getByRole('button', { name: '已阅读，返回登录' }).click()
    await page.getByLabel('学号', { exact: true }).fill('000000000000')
    await page.getByLabel('密码', { exact: true }).fill('synthetic-demo-only')
    const captcha = (await page.getByRole('button', { name: '刷新验证码' }).innerText()).match(/(\d+)\s*\+\s*(\d+)/)
    if (!captcha) throw new Error('参考验证码结构改变')
    await page.getByPlaceholder('请输入计算结果').fill(String(Number(captcha[1]) + Number(captcha[2])))
    await page.getByLabel('同意用户协议', { exact: true }).check()
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await page.getByRole('heading', { name: '总览', exact: true }).waitFor()
    await capture('overview')
    await page.getByRole('button', { name: '电费明细', exact: true }).click()
    await capture('details')
    await page.locator('.date-field').first().click()
    await capture('calendar')
    await page.getByRole('button', { name: '关闭日历' }).click()
    await page.getByRole('button', { name: '电费缴费', exact: true }).click()
    await capture('payment')
    await page.getByRole('button', { name: '关闭弹窗' }).click()
    await page.getByRole('button', { name: '选择与绑定', exact: true }).click()
    await capture('rooms')
    await page.getByRole('button', { name: '新增绑定', exact: true }).click()
    await capture('binding')
    await page.getByRole('button', { name: '关闭弹窗' }).click()
    await page.getByRole('button', { name: '监控与预警', exact: true }).click()
    await capture('monitor')
    await context.close()
  }
  await writeFile(`${output}/manifest.json`, JSON.stringify({ source: 'example/nature.html',
    synthetic: true, viewport_height: 1000, captures }, null, 2) + '\n')
  console.log(`已保存 ${captures.length} 张参考截图（全部为合成演示数据）`)
} finally {
  await browser.close()
}

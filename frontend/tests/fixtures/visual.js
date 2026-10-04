import { readFileSync } from 'node:fs'
import { agreement, bindings, captcha, envelope, me } from './t2.js'
import { monitor } from './t3.js'
import { a, balance, sample } from './t4.js'
import { addDays } from '../../src/lib/dates.js'

// 与 example 的截图采用相同合成账号、房间和总览趋势；明细数据独立合成，仅由测试拦截 API 使用。
const captchaImage = 'data:image/png;base64,' + readFileSync(new URL('./visual-captcha.png', import.meta.url)).toString('base64')
const amounts = ['3.20', '4.50', '3.80', '5.90', '4.70', '3.50', '4.20', '5.30', '4.10', '3.70', '4.80', '3.60', '4.40', '3.90']
const currentBalance = { ...balance('86.42'), fetched_at: '2026-10-01T10:00:00+08:00', stale: false }
const room = { id: a, room_id: a, display_name: '合成楼 · 示例室', building: '合成楼', number: '示例室', status: 'active', balance: currentBalance }
const user = { ...me, student_id: '000000000000' }
/** @param {string} start @param {string} end @param {string} [granularity] */
function history(start, end, granularity = 'day') {
  const days = Math.round((Date.parse(end) - Date.parse(start)) / 86400000) + 1
  const buckets = Array.from({ length: days }, (_, i) => ({ start_date: addDays(start, i), end_date: addDays(start, i), amount: amounts[i % amounts.length], energy_usage: null, known_days: 1, expected_days: 1, complete: true }))
  const total = (buckets.reduce((sum, bucket) => sum + Number(bucket.amount) * 100, 0) / 100).toFixed(2)
  return { binding_id: a, start_date: start, end_date: end, granularity, buckets,
    summary: { amount: total, energy_usage: null, known_days: days, expected_days: days, complete: true }, coverage: 'complete', sync_status: 'ready', sync_operation: null, version: 1 }
}
/** @param {import('@playwright/test').Page} page */
export async function visualFixture(page) {
  let logged = true
  const unexpected = []
  const wrap = data => ({ ...envelope(data), meta: { ...envelope(data).meta, server_time: '2026-10-01T10:00:00+08:00' } })
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    const send = data => route.fulfill({ json: wrap(data) })
    if (path === '/api/v1/auth/logout') { logged = false; return route.fulfill({ status: 204 }) }
    if (path === '/api/v1/auth/me') return logged ? send(user) : route.fulfill({ status: 401, json: { error: { code: 'APP_SESSION_EXPIRED' } } })
    if (path === '/api/v1/auth/agreement') return send(agreement)
    if (path === '/api/v1/auth/captcha') return send({ ...captcha(), image_data_url: captchaImage })
    if (request.method() !== 'GET') { unexpected.push(`${request.method()} ${path}`); return route.abort() }
    if (path === '/api/v1/room-bindings') return send({ ...bindings, items: [room], total: 1, default_binding_id: a, sync_status: 'ready' })
    if (path === '/api/v1/overview') return send({ viewing_binding_id: a,
      profile: { student_id: user.student_id, default_binding: room, alert_email: 'fixture@example.invalid' }, balance: currentBalance,
      summary: { yesterday_amount: '3.90', last_14_days_amount: '59.60', known_days: 14, expected_days: 14, complete: true },
      daily_consumption: history('2026-09-17', '2026-09-30'), monitor: { enabled: true, state: 'active', health: 'healthy', interval_minutes: 60 },
      component_status: { profile: 'ready', balance: 'ready', history: 'ready', monitor: 'ready' } })
    if (path.endsWith('/balance')) return send(currentBalance)
    if (path.endsWith('/consumption')) return send(history(url.searchParams.get('start_date'), url.searchParams.get('end_date'), url.searchParams.get('granularity')))
    if (path.endsWith('/monitor-samples')) return send({ binding_id: a, items: Array.from({ length: 10 }, (_, i) => ({ ...sample(i), balance: '86.42', captured_at: `2026-10-01T${String(23 - i).padStart(2, '0')}:00:00+08:00` })), total: 10, page: 1, page_size: 10, has_monitor_history: true, snapshot_token: 'visual-synthetic' })
    if (path === '/api/v1/monitor') return send({ ...monitor(), binding_id: a, health: 'healthy', config: { ...monitor().config, email: 'fixture@example.invalid' } })
    if (path === '/api/v1/room-candidates/buildings') return send({ items: [{ id: 'visual-1', label: '合成甲楼' }, { id: 'visual-2', label: '合成乙楼' }] })
    if (path === '/api/v1/payments/capabilities') return send({ enabled: false, min_amount: '1.00', max_amount: '500.00', amount_step: '1.00', currency: 'CNY', unresolved_order: null, unavailable_reason: '支付暂未开放' })
    unexpected.push(`${request.method()} ${path}`)
    return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND' } } })
  })
  return unexpected
}

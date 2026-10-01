import { addDays } from '../../src/lib/dates.js'
import { bindings } from './t2.js'

export const a = '0199a10c-0000-7000-8000-000000000003'
export const b = '0199a10c-0000-7000-8000-000000000004'
export const runId = '0199a10c-0000-7000-8000-000000000005'
/** @param {string} amount @returns {import('../../src/api/generated').components['schemas']['Balance']} */
export const balance = amount => ({ amount, currency: 'CNY', source: 'school_bound_rooms', fetched_at: '2026-10-01T09:00:00+08:00', school_observed_at: null, stale: true, refresh_state: 'ready', error_code: null })
export const rooms = { ...bindings, default_binding_id: a, sync_status: 'ready', total: 2,
  items: [{ id: a, room_id: a, display_name: '合成甲楼 101', building: '合成甲楼', number: '101', status: 'active', balance: balance('12.34') },
    { id: b, room_id: b, display_name: '合成乙楼 202', building: '合成乙楼', number: '202', status: 'active', balance: balance('98.76') }] }

/** @param {string} start @param {string} end @param {'day'|'week'|'month'} [granularity] @returns {import('../../src/api/generated').components['schemas']['Consumption']} */
export function consumption(start, end, granularity = 'day') {
  const days = (Date.parse(end) - Date.parse(start)) / 86_400_000 + 1
  const buckets = Array.from({ length: days }, (_, i) => ({ start_date: addDays(start, i), end_date: addDays(start, i),
    amount: i === 0 ? '0.00' : i === days - 1 ? '1.50' : null, energy_usage: null, known_days: i === 0 || i === days - 1 ? 1 : 0, expected_days: 1, complete: false }))
  return { binding_id: a, start_date: start, end_date: end, granularity,
    buckets: granularity === 'day' ? buckets : [{ start_date: start, end_date: end, amount: '1.50', energy_usage: null, known_days: 2, expected_days: days, complete: false }],
    summary: { amount: '1.50', energy_usage: null, known_days: 2, expected_days: days, complete: false }, coverage: 'partial', sync_status: 'partial', sync_operation: null, version: 1 }
}

/** @param {number} index @returns {import('../../src/api/generated').components['schemas']['Sample']} */
export const sample = index => ({ id: `0199a10c-0000-7000-8000-${String(index + 100).padStart(12, '0')}`, run_id: runId,
  captured_at: '2026-10-01T10:00:00+08:00', balance: '12.34', previous_captured_at: index === 10 ? null : '2026-10-01T09:00:00+08:00', balance_delta: index === 10 ? null : '-1.20', balance_delta_kind: 'net_balance_change',
  gap_seconds: index === 10 ? null : 3600, gap_detected: false, meter_last_reading: null, meter_reading: null, meter_delta: null, meter_record_date: null, meter_source: null, meter_source_record_key: null, meter_is_repeated: false, quality: 'balance_only' })

/** @param {import('../../src/api/generated').components['schemas']['Run']['state']} state @returns {import('../../src/api/generated').components['schemas']['Run']} */
export const run = state => ({ id: runId, binding_id: a, state, version: state === 'running' ? 2 : 3,
  scheduled_for: '2026-10-01T10:00:00+08:00', started_at: '2026-10-01T10:00:00+08:00', finished_at: state === 'cancelled' ? '2026-10-01T10:00:05+08:00' : null,
  next_attempt_at: null, cancel_pending: state === 'cancel_requested', error_code: null,
  attempts: [{ attempt_no: 1, started_at: '2026-10-01T10:00:00+08:00', finished_at: null, outcome: 'running', error_code: null }] })

export const emptyOverview = { viewing_binding_id: null, profile: null, balance: null, summary: null, daily_consumption: null, monitor: null,
  component_status: { profile: 'unavailable', balance: 'empty', history: 'empty', monitor: 'unavailable' } }

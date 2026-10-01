import { me } from './t2.js'

/** @returns {import('../../src/api/generated').components['schemas']['Monitor']} */
export function monitor() {
  return { id: me.id, binding_id: me.id, config: { enabled: true, interval_minutes: 60, repeat_limit: 2,
    threshold: '20.00', email: 'synthetic@example.invalid' }, state: 'active', health: 'unavailable',
    version: 1, generation: 1, current_run: null, last_run: null, next_run_at: null,
    last_success_at: null, last_error_code: null, in_flight_count: 0, cancel_pending: false,
    notification: { state: 'idle', last_sent_at: null, last_error_code: null, next_retry_at: null,
      in_flight_count: 0, delivery_unknown_count: 0 } }
}

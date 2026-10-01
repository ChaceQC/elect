import { me } from './t2.js'

export const bindingId = '0199a10c-0000-7000-8000-000000000003'
export const orderId = '0199a10c-0000-7000-8000-000000000030'
export const capability = { enabled: true, currency: 'CNY', min_amount: '1.00', max_amount: '500.00',
  amount_step: '1.00', unavailable_reason: null, unresolved_order: null, amount_policy_source: 'application_policy' }
/** @type {import('../../src/api/generated').components['schemas']['Order']} */
export const order = { order_id: orderId, binding_id: bindingId, state: 'status_unknown', amount: '20.00',
  version: 1, cancel_pending: false, cancelled_at: null,
  currency: 'CNY', created_at: '2026-10-02T02:00:00+08:00', binding_display_name: '合成默认楼-402',
  paid_confirmed: false, last_checked_at: null, qr_status: 'unknown', qr_expires_at: null,
  error_code: null, qr_error_code: null, balance_refresh_state: 'not_required', balance_refresh_operation_id: null }
export const binding = { id: bindingId, room_id: bindingId, display_name: '合成默认楼-402', building: '合成默认楼',
  number: '402', status: 'active', balance: null }
export const owner = me.id

export const requestId = '0199a10c-0000-7000-8000-000000000001'
export const me = { id: requestId, student_id: 'synthetic', school: '合成测试学校', csrf_token: 'synthetic-csrf',
  credential_status: 'active', credential_version: 1, credential_revoke_operation: null,
  consent: { agreement_version: 'test', accepted_at: '2026-10-01T10:00:00+08:00',
    credential_use_allowed: true, revoked_at: null } }
export const agreement = { version: 'test', content: '合成测试使用协议。', content_hash: 'a'.repeat(64),
  updated_at: '2026-10-01T10:00:00+08:00' }
export const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg=='
export const captcha = (id = 'a') => ({ challenge_id: id.repeat(43), image_data_url: image,
  expires_at: new Date(Date.now() + 120_000).toISOString() })
export const bindings = { items: [], page: 1, page_size: 10, total: 0, default_binding_id: null,
  preference_version: 1, default_switch_operation_id: null, sync_status: 'empty',
  last_synced_at: '2026-10-01T10:00:00+08:00', pending_operations: [], pending_operations_truncated: false }
/** @template T @param {T} data */
export const envelope = (data) => ({ data, meta: { request_id: requestId } })

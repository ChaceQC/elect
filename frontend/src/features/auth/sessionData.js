import { ApiError } from '../../api/client.js'

/** @typedef {import('../../api/generated').components['schemas']['LocalSession']} LocalSession */
/** @typedef {import('../../api/generated').components['schemas']['Me']} Me */

/** @param {unknown} input @returns {LocalSession} */
export function parseLocal(input) {
  const value = /** @type {LocalSession} */ (input)
  if (!value || typeof value.id !== 'string' || !/^[0-9a-f-]{36}$/i.test(value.id) ||
    typeof value.csrf_token !== 'string' || !value.csrf_token || !value.consent ||
    typeof value.consent.credential_use_allowed !== 'boolean') {
    throw new ApiError('INVALID_RESPONSE', '无法识别当前会话，请重新检查', 200)
  }
  return { id: value.id, csrf_token: value.csrf_token, consent: value.consent }
}

/** @param {unknown} input @returns {Me} */
export function parseProfile(input) {
  parseLocal(input)
  const value = /** @type {Me} */ (input)
  if (typeof value.school !== 'string' || typeof value.student_id !== 'string' ||
    !['active', 'requires_reauth', 'revoking', 'revoked', 'missing'].includes(value.credential_status)) {
    throw new ApiError('INVALID_RESPONSE', '无法识别学校资料，请稍后重试', 200)
  }
  return value
}

import Decimal from 'decimal.js'

/** @typedef {import('../../api/generated').components['schemas']['Monitor']} Monitor */
/** @typedef {{enabled: boolean, interval_minutes: string, repeat_limit: string, threshold: string, email: string}} Draft */
/** @param {Monitor} monitor @returns {Draft} */
export function draftFrom(monitor) {
  return { ...monitor.config, interval_minutes: String(monitor.config.interval_minutes),
    repeat_limit: String(monitor.config.repeat_limit), email: monitor.config.email ?? '' }
}
/** @param {Draft} draft */
export function parseDraft(draft) {
  if (!/^\d+$/.test(draft.interval_minutes) || !Number.isInteger(Number(draft.interval_minutes)) ||
    Number(draft.interval_minutes) < 60 || Number(draft.interval_minutes) > 1440) throw new Error('采集间隔须为 60–1440 的整数分钟。')
  if (!/^[1-5]$/.test(draft.repeat_limit)) throw new Error('提醒总次数须为 1–5。')
  if (!/^\d+(\.\d{1,2})?$/.test(draft.threshold) || new Decimal(draft.threshold).lte(0) ||
    new Decimal(draft.threshold).gt(10000)) throw new Error('低余额阈值须大于 0 且不超过 10000 元，最多两位小数。')
  const email = draft.email.trim()
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || draft.enabled && !email) throw new Error('请输入有效的提醒邮箱。')
  return { enabled: draft.enabled, interval_minutes: Number(draft.interval_minutes),
    repeat_limit: Number(draft.repeat_limit), threshold: new Decimal(draft.threshold).toFixed(2), email: email || null }
}

let serverOffset = 0
/** @param {number} [now] */
export const serverNow = (now = Date.now()) => now + serverOffset
/** @param {string|undefined} timestamp */
export function calibrateTime(timestamp) {
  if (timestamp && Number.isFinite(Date.parse(timestamp))) serverOffset = Date.parse(timestamp) - Date.now()
}
/** @param {Date} [now] */
export function shanghaiDate(now = new Date(Date.now() + serverOffset)) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type)?.value).join('-')
}
/** @param {string} date @param {number} days */
export function addDays(date, days) {
  const value = new Date(`${date}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}
/** @param {string} start @param {string} end */
export function selectableRange(start, end) { return validDateRange(start, end) && end <= shanghaiDate() }
/** @param {string|null} value */
export const timestampLabel = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '暂无'
/** @param {string} start @param {string} end */
export function validDateRange(start, end) {
  const dates = [start, end].map(value => new Date(`${value}T00:00:00Z`))
  if (dates.some((date, index) => Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== [start, end][index])) return false
  const days = (dates[1].getTime() - dates[0].getTime()) / 86_400_000 + 1
  return days >= 1 && days <= 366
}

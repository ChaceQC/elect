/** @param {Date} [now] */
export function shanghaiDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type)?.value).join('-')
}
/** @param {string} start @param {string} end */
export function validDateRange(start, end) {
  const dates = [start, end].map(value => new Date(`${value}T00:00:00Z`))
  if (dates.some((date, index) => Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== [start, end][index])) return false
  const days = (dates[1].getTime() - dates[0].getTime()) / 86_400_000 + 1
  return days >= 1 && days <= 366
}

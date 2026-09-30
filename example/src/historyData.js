// Fixed dates match the rest of this demonstration; no school data is requested.
export const DEMO_TODAY = '2026-10-01'
const DAY = 86400000
export const shiftDate = (date, days) => new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY).toISOString().slice(0, 10)
export const recentRange = days => ({ start: shiftDate(DEMO_TODAY, 1 - days), end: DEMO_TODAY })
export const dailyHistory = Array.from({ length: 180 }, (_, i) => ({
  date: shiftDate(DEMO_TODAY, i - 179),
  cents: 280 + (i * 73 % 340),
}))
export function filterHistory(range) {
  return dailyHistory.filter(day => day.date >= range.start && day.date <= range.end)
}
export function aggregateHistory(days, period) {
  const buckets = new Map()
  days.forEach(day => {
    const weekday = new Date(`${day.date}T00:00:00Z`).getUTCDay()
    const key = period === 'month' ? day.date.slice(0, 7) : period === 'week' ? shiftDate(day.date, -((weekday + 6) % 7)) : day.date
    const bucket = buckets.get(key) || { start: day.date, end: day.date, cents: 0 }
    bucket.end = day.date
    bucket.cents += day.cents
    buckets.set(key, bucket)
  })
  return [...buckets.values()].map(bucket => ({ label: bucket.start === bucket.end ? bucket.start : `${bucket.start} ~ ${bucket.end}`, value: bucket.cents / 100 }))
}
export function monitorHistory(balance, range) {
  let currentCents = Math.round(balance * 100)
  let currentMeter = 500000
  const rows = []
  for (const day of [...dailyHistory].reverse()) {
    for (let slot = 5; slot >= 0; slot--) {
      const cents = Math.floor(day.cents / 6) + (slot < day.cents % 6 ? 1 : 0)
      const units = Math.round(cents / .56)
      rows.push({ date: day.date, time: `${day.date} ${String(slot * 4 + 3).padStart(2, '0')}:00`, balance: currentCents / 100, delta: -cents / 100, previousMeter: (currentMeter - units) / 100, currentMeter: currentMeter / 100, units: units / 100 })
      currentCents += cents
      currentMeter -= units
    }
  }
  return rows.filter(row => row.date >= range.start && row.date <= range.end)
}

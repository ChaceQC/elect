import Decimal from 'decimal.js'

/** @param {string|null} value */
export function moneyLabel(value) { return value === null ? '—' : `¥${new Decimal(value).toFixed(2)}` }

/** @param {string} value @param {{minimum: string, maximum: string, step: string}} limits */
export function validateAmount(value, limits) {
  if (!/^(0|[1-9]\d*)\.\d{2}$/.test(value)) return false
  const amount = new Decimal(value)
  return amount.isFinite() && amount.gte(limits.minimum) && amount.lte(limits.maximum) &&
    amount.minus(limits.minimum).mod(limits.step).isZero()
}

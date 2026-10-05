/** @param {{stale: boolean, fetched_at: string|null}|null|undefined} balance @param {number} now */
export function isBalanceStale(balance, now) {
  const fetched = balance?.fetched_at ? Date.parse(balance.fetched_at) : NaN
  return !balance || balance.stale || !Number.isFinite(fetched) || now - fetched > 300_000
}

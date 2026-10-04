import { apiClient } from './client.js'

const terminal = {
  operation: new Set(['succeeded', 'failed', 'cancelled']),
  run: new Set(['succeeded', 'failed', 'cancelled']),
  order: new Set(['paid_confirmed', 'rejected', 'expired_confirmed', 'closed_confirmed']),
}
/** @typedef {import('./intents.js').ResourceKind} ResourceKind */
/** @typedef {{id: string, state: string, type?: string}} OperationResource */
/** @param {ResourceKind} kind @param {string|undefined} state */
export const isTerminal = (kind, state) => state !== undefined && terminal[kind].has(state)

/** @param {ResourceKind} kind @param {string} id @param {AbortSignal} [signal] */
export async function readOperation(kind, id, signal) {
  const path = { operation: '/operations', run: '/monitor/runs', order: '/payment-orders' }[kind]
  const result = await apiClient.request(`${path}/${encodeURIComponent(id)}`, { signal })
  return /** @type {OperationResource} */ (result.data)
}

/** @param {ResourceKind} kind @param {string|undefined} state @param {number} elapsedMs @param {boolean} visible @param {string} [operationType] */
export function pollInterval(kind, state, elapsedMs, visible, operationType) {
  if (!visible || isTerminal(kind, state)) return false
  if (kind === 'order' || operationType === 'unbind_room') return 2000
  if (elapsedMs >= 120_000) return false
  return elapsedMs < 20_000 ? 2000 : elapsedMs < 60_000 ? 5000 : 10_000
}

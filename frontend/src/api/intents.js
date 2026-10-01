import { apiClient } from './client.js'

/** @typedef {'operation'|'run'|'order'} ResourceKind */
/** @typedef {Record<string,string|number|boolean|null>} SafeBody */
/** @typedef {{key: string, path: string, body: SafeBody, kind: ResourceKind,
 * id: string|null, createdAt: number, method?: 'POST'|'DELETE'}} Intent */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const fields = new Set(['candidate_id', 'binding_id', 'amount', 'expected_version', 'make_default',
  'start_date', 'end_date'])
const safePath = /^\/(room-bindings(?:\/sync|\/[0-9a-f-]{36}\/(?:balance-refresh|history-sync))?|monitor\/runs|payment-orders(?:\/[0-9a-f-]{36}\/qr-refresh)?)$/i

const deletePath = /^\/room-bindings\/[0-9a-f-]{36}$/i
/** @param {string} path @param {string} [method] */
const safeRequest = (path, method = 'POST') => method === 'DELETE' ? deletePath.test(path) : method === 'POST' && safePath.test(path)

function availableStorage() {
  try { return sessionStorage } catch { return null }
}
/** @param {string} userId @param {Storage|null} [storage] */
export function clearRecovery(userId, storage = availableStorage()) {
  if (!storage) return
  try {
    for (const key of Object.keys(storage)) if (key.startsWith(`elect.intent.${userId}.`)) storage.removeItem(key)
  } catch { /* 浏览器禁用存储时仍可清理内存会话。 */ }
}

/** @param {unknown} body @returns {SafeBody} */
function sanitize(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('操作请求必须是对象')
  const result = /** @type {SafeBody} */ ({})
  for (const [key, value] of Object.entries(body).sort(([a], [b]) => a.localeCompare(b))) {
    if (!fields.has(key) || !['string', 'number', 'boolean'].includes(typeof value) && value !== null) {
      throw new Error('操作恢复记录不允许敏感或嵌套字段')
    }
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('非法数字')
    if (typeof value === 'string' && value.length > 128) throw new Error('字段过长')
    result[key] = value
  }
  return Object.freeze(result)
}

export class OperationController {
  /** @param {string} userId @param {import('./client.js').ApiClient} [client] @param {Storage|null} [storage] */
  constructor(userId, client = apiClient, storage = availableStorage()) {
    if (!UUID.test(userId)) throw new Error('操作恢复需要有效的用户 ID')
    this.userId = userId
    this.client = client
    this.storage = storage
    /** @type {Map<string,Intent>} */ this.memory = new Map()
    /** @type {Set<string>} */ this.persisted = new Set()
    /** @type {Map<string,Promise<Intent>>} */ this.inFlight = new Map()
  }

  /** @param {Intent} intent */
  remember(intent) {
    this.memory.set(intent.key, intent)
    try {
      if (this.storage) {
        this.storage.setItem(`elect.intent.${this.userId}.${intent.key}`, JSON.stringify(intent))
        this.persisted.add(intent.key)
      }
    }
    catch { /* 存储不可用时保留本次内存记录，服务端摘要负责刷新恢复。 */ }
    return intent
  }

  /** @param {string} path @param {SafeBody} [body] @param {ResourceKind} [kind] @param {'POST'|'DELETE'} [method] */
  create(path, body = {}, kind = 'operation', method = 'POST') {
    if (!safeRequest(path, method)) throw new Error('仅登记的幂等接口可保存重试请求')
    return this.remember(Object.freeze({ key: crypto.randomUUID(), path, body: sanitize(body), kind, method,
      id: null, createdAt: Date.now() }))
  }

  /** @param {Intent} intent */
  async submit(intent) {
    if (intent.id) return intent
    const previous = this.inFlight.get(intent.key)
    if (previous) return previous
    const pending = this.send(intent)
    this.inFlight.set(intent.key, pending)
    try { return await pending } finally { this.inFlight.delete(intent.key) }
  }

  /** @param {Intent} intent */
  async send(intent) {
    const result = await this.client.request(intent.path, { method: intent.method ?? 'POST', body: intent.method === 'DELETE' ? undefined : intent.body,
      headers: { 'Idempotency-Key': intent.key } })
    const field = { operation: 'operation_id', run: 'run_id', order: 'order_id' }[intent.kind]
    const id = result.data?.[field]
    if (result.status !== 202 || typeof id !== 'string' || !UUID.test(id)) throw new Error('操作未返回有效受理标识')
    return this.remember(Object.freeze({ ...intent, id }))
  }

  /** @returns {Intent[]} */
  restore() {
    try {
      for (const key of this.persisted) {
        if (this.storage?.getItem(`elect.intent.${this.userId}.${key}`) === null) {
          this.memory.delete(key); this.persisted.delete(key)
        }
      }
      for (const key of Object.keys(this.storage ?? {})) {
        if (!key.startsWith(`elect.intent.${this.userId}.`)) continue
        try {
          const item = JSON.parse(this.storage?.getItem(key) ?? '')
          if (!UUID.test(item.key) || (!safeRequest(item.path, item.method ?? 'POST') && !(item.path === '' && UUID.test(item.id))) ||
            !['operation', 'run', 'order'].includes(item.kind) ||
            !(item.id === null || typeof item.id === 'string' && UUID.test(item.id)) ||
            !Number.isFinite(item.createdAt) || key !== `elect.intent.${this.userId}.${item.key}`) throw new Error('invalid')
          this.memory.set(item.key, Object.freeze({ key: item.key, path: item.path, kind: item.kind,
            id: item.id, createdAt: item.createdAt, method: item.method ?? 'POST', body: sanitize(item.body) }))
          this.persisted.add(item.key)
        } catch { this.storage?.removeItem(key) }
      }
    } catch { /* sessionStorage 可被浏览器策略禁用。 */ }
    return [...this.memory.values()]
  }

  /** @param {ResourceKind} kind @param {string[]} ids */
  recoverSummaries(kind, ids) {
    const recovered = this.restore()
    for (const id of ids) {
      if (!UUID.test(id) || recovered.some(item => item.id === id && item.kind === kind)) continue
      recovered.push(this.remember({ key: crypto.randomUUID(), path: '', body: {}, kind, id, createdAt: Date.now() }))
    }
    return recovered
  }

  /** @param {string} key */
  forget(key) {
    this.memory.delete(key)
    this.persisted.delete(key)
    try { this.storage?.removeItem(`elect.intent.${this.userId}.${key}`) } catch { /* 无可清理记录。 */ }
  }
}

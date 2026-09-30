/** @typedef {{request_id: string, server_time?: string}} Meta */
/** @typedef {{retryable?: boolean, retry_after_seconds?: number|null, requires_reauth?: boolean,
 * field_errors?: Record<string,string>, current_version?: number|null,
 * existing_operation_id?: string|null, requestId?: string|null}} ErrorDetails */
/** @typedef {{method?: string, body?: unknown, headers?: Record<string,string>, signal?: AbortSignal,
 * timeoutMs?: number}} RequestOptions */

export class ApiError extends Error {
  /** @param {string} code @param {string} message @param {number} status @param {ErrorDetails} [details] */
  constructor(code, message, status, details = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.retryable = details.retryable ?? false
    this.retryAfterSeconds = details.retry_after_seconds ?? null
    this.requiresReauth = details.requires_reauth ?? false
    this.fieldErrors = details.field_errors ?? {}
    this.currentVersion = details.current_version ?? null
    this.existingOperationId = details.existing_operation_id ?? null
    this.requestId = details.requestId ?? null
  }
}

/** @param {Response} response */
function retryAfter(response) {
  const value = response.headers.get('Retry-After')
  if (!value) return null
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return Math.max(0, seconds)
  const date = Date.parse(value)
  return Number.isNaN(date) ? null : Math.max(0, Math.ceil((date - Date.now()) / 1000))
}

/** @param {Response} response */
async function decode(response) {
  if (response.status === 204) return { data: null, meta: null, status: 204 }
  const document = await response.json().catch(() => null)
  const requestId = document?.meta?.request_id ?? response.headers.get('X-Request-ID')
  if (!response.ok) {
    const error = document?.error
    throw new ApiError(error?.code ?? (response.status === 429 ? 'RATE_LIMITED' : 'HTTP_ERROR'),
      error?.message ?? '请求未完成，请稍后重试', response.status, {
        ...error, requestId,
        retryable: error?.retryable ?? [429, 502, 503, 504].includes(response.status),
        retry_after_seconds: retryAfter(response) ?? error?.retry_after_seconds,
      })
  }
  if (!document || !('data' in document) || typeof document.meta?.request_id !== 'string') {
    throw new ApiError('INVALID_RESPONSE', '服务返回了无法识别的结果', response.status, { requestId })
  }
  return { data: document.data, meta: /** @type {Meta} */ (document.meta), status: response.status }
}

export class ApiClient {
  /** @param {typeof fetch} [fetcher] */
  constructor(fetcher = (...args) => fetch(...args)) {
    this.fetcher = fetcher
    /** @type {string|null} */ this.csrfToken = null
    /** @type {Set<AbortController>} */ this.controllers = new Set()
    /** @type {(()=>void)|null} */ this.onSessionExpired = null
    this.epoch = 0
  }

  reset() {
    this.epoch += 1
    this.csrfToken = null
    for (const controller of this.controllers) controller.abort()
    this.controllers.clear()
  }

  /** @param {string} path @param {RequestOptions} [options] */
  async request(path, options = {}) {
    if (!path.startsWith('/') || path.startsWith('//')) throw new Error('API 路径必须同源')
    const url = new URL(path.startsWith('/api/v1/') ? path : `/api/v1${path}`, location.origin)
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/v1/')) {
      throw new Error('API 路径必须位于 /api/v1')
    }
    const method = (options.method ?? 'GET').toUpperCase()
    const headers = new Headers(options.headers)
    headers.set('Accept', 'application/json')
    headers.set('X-Request-ID', crypto.randomUUID())
    if (options.body !== undefined) headers.set('Content-Type', 'application/json')
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && this.csrfToken) {
      headers.set('X-CSRF-Token', this.csrfToken)
    }
    const controller = new AbortController()
    const epoch = this.epoch
    this.controllers.add(controller)
    const signal = options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal
    let timedOut = false
    const timer = setTimeout(() => { timedOut = true; controller.abort() },
      options.timeoutMs ?? (path === '/auth/login' ? 75_000 : 40_000))
    try {
      const response = await this.fetcher(url.pathname + url.search, {
        method, headers, signal, credentials: 'same-origin', cache: 'no-store',
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      })
      const result = await decode(response)
      signal.throwIfAborted()
      if (epoch !== this.epoch) throw new DOMException('会话已改变', 'AbortError')
      return result
    } catch (error) {
      if (epoch !== this.epoch) throw new DOMException('会话已改变', 'AbortError')
      if (error instanceof ApiError) {
        if (error.code === 'APP_SESSION_EXPIRED' && epoch === this.epoch) this.onSessionExpired?.()
        throw error
      }
      if (timedOut) throw new ApiError('REQUEST_TIMEOUT', '等待服务超时，请查询当前结果后重试', 0, { retryable: true })
      if (signal.aborted) throw new DOMException('已停止等待', 'AbortError')
      throw new ApiError('NETWORK_ERROR', '网络连接失败，请检查连接后重试', 0, { retryable: true })
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }
}

export const apiClient = new ApiClient()

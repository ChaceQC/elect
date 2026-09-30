import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiError } from '../../src/api/client.js'

const meta = { request_id: '0199a10c-0000-7000-8000-000000000001' }
/** @param {unknown} data @param {number} [status] */
const success = (data, status = 200) => Response.json({ data, meta }, { status })
afterEach(() => vi.useRealTimers())

describe('API 客户端', () => {
  it('使用同源 Cookie、内存 CSRF，正确处理 204 和响应信封', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(success({ value: null }))
    const client = new ApiClient(fetcher)
    client.csrfToken = 'test-csrf'
    expect((await client.request('/auth/logout', { method: 'POST' })).data).toBeNull()
    const [path, options] = fetcher.mock.calls[0]
    expect(path).toBe('/api/v1/auth/logout')
    expect(options.credentials).toBe('same-origin')
    expect(options.headers.get('X-CSRF-Token')).toBe('test-csrf')
    expect((await client.request('/overview')).data).toEqual({ value: null })
    await expect(client.request('//foreign.example/api')).rejects.toThrow('同源')
    await expect(client.request('/api/v1/../../private')).rejects.toThrow('/api/v1')
  })

  it('按 code 区分应用会话过期和学校认证异常，并保留 429/503 语义', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ error: { code: 'SCHOOL_REAUTH_REQUIRED' }, meta }, { status: 409 }))
      .mockResolvedValueOnce(Response.json({ error: { code: 'APP_SESSION_EXPIRED' }, meta }, { status: 401 }))
      .mockResolvedValueOnce(new Response('rate limited', { status: 429, headers: { 'Retry-After': '7' } }))
      .mockResolvedValueOnce(Response.json({ error: { code: 'DEPENDENCY_UNAVAILABLE', retryable: true }, meta }, { status: 503 }))
    const client = new ApiClient(fetcher)
    client.onSessionExpired = vi.fn()
    await expect(client.request('/monitor')).rejects.toMatchObject({ code: 'SCHOOL_REAUTH_REQUIRED' })
    expect(client.onSessionExpired).not.toHaveBeenCalled()
    await expect(client.request('/auth/me')).rejects.toMatchObject({ code: 'APP_SESSION_EXPIRED' })
    expect(client.onSessionExpired).toHaveBeenCalledOnce()
    await expect(client.request('/overview')).rejects.toMatchObject({ status: 429, retryAfterSeconds: 7 })
    await expect(client.request('/overview')).rejects.toMatchObject({ status: 503, retryable: true })
  })

  it('请求取消、超时和切换会话后的迟到响应均不产生成功结果', async () => {
    const fetcher = vi.fn((_, options) => new Promise((resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new DOMException('abort', 'AbortError')))
    }))
    const client = new ApiClient(fetcher)
    const controller = new AbortController()
    const pending = client.request('/overview', { signal: controller.signal })
    const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort(); await rejected
    vi.useFakeTimers()
    const timed = client.request('/overview', { timeoutMs: 5 })
    const timeout = expect(timed).rejects.toMatchObject({ code: 'REQUEST_TIMEOUT' })
    await vi.advanceTimersByTimeAsync(5); await timeout
    vi.useRealTimers()
    /** @type {(value:Response)=>void} */ let finish = () => {}
    const lateClient = new ApiClient(vi.fn(() => new Promise(resolve => { finish = resolve })))
    const late = lateClient.request('/overview')
    lateClient.reset(); finish(success({ previous_user: true }))
    await expect(late).rejects.toMatchObject({ name: 'AbortError' })
    expect(client.controllers.size).toBe(0)
  })

  it('不显示或缓存不完整的成功结果', async () => {
    const client = new ApiClient(vi.fn().mockResolvedValue(Response.json({ value: 0 })))
    await expect(client.request('/overview')).rejects.toBeInstanceOf(ApiError)
  })
})

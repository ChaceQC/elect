import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, apiClient } from '../../api/client.js'

/** @typedef {import('../../api/generated').components['schemas']['Captcha']} Captcha */
export function useCaptcha() {
  const [data, setData] = useState(/** @type {Captcha|null} */ (null))
  const [error, setError] = useState(/** @type {ApiError|null} */ (null))
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(Date.now())
  const sequence = useRef(0)
  const pending = useRef(/** @type {AbortController|null} */ (null))
  const previous = useRef(/** @type {string|null} */ (null))
  const refresh = useCallback(async () => {
    const generation = ++sequence.current
    pending.current?.abort()
    pending.current = new AbortController()
    setData(null); setError(null); setBusy(true)
    try {
      const response = await apiClient.request('/auth/captcha', { method: 'POST',
        body: { previous_challenge_id: previous.current }, signal: pending.current.signal })
      if (generation !== sequence.current) return
      const challenge = /** @type {Captcha} */ (response.data)
      if (!challenge?.challenge_id || !/^data:image\/(png|jpeg);base64,/.test(challenge.image_data_url) ||
        !Number.isFinite(Date.parse(challenge.expires_at))) throw new ApiError('INVALID_RESPONSE', '验证码响应异常', 200)
      previous.current = challenge.challenge_id
      setData(challenge); setNow(Date.now())
    } catch (cause) {
      if (generation === sequence.current && !(cause instanceof DOMException && cause.name === 'AbortError')) {
        setError(cause instanceof ApiError ? cause : new ApiError('NETWORK_ERROR', '无法获取验证码', 0))
      }
    } finally { if (generation === sequence.current) setBusy(false) }
  }, [])
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    const requests = pending, counter = sequence
    return () => { clearInterval(timer); ++counter.current; requests.current?.abort() }
  }, [])
  return { data, error, busy, refresh, expired: !!data && Date.parse(data.expires_at) <= now }
}

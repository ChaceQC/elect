import { useEffect, useMemo, useState } from 'react'
import { OperationController } from '../api/intents.js'
import { ApiError } from '../api/client.js'
import { useSession } from '../features/auth/SessionProvider.jsx'

export function useRequestIntent() {
  const { user } = useSession()
  const controller = useMemo(() => user ? new OperationController(user.id) : null, [user])
  const [busy, setBusy] = useState(false)
  const [retryAt, setRetryAt] = useState(0)
  useEffect(() => {
    if (!retryAt) return
    const timer = setTimeout(() => setRetryAt(0), Math.max(0, retryAt - Date.now()))
    return () => clearTimeout(timer)
  }, [retryAt])
  useEffect(() => { setRetryAt(0) }, [controller])
  /** @param {import('../api/intents.js').Intent} intent */
  async function submit(intent) {
    if (!controller) throw new Error('请先登录')
    setBusy(true)
    try { return await controller.submit(intent) }
    catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        const seconds = Math.max(1, error.retryAfterSeconds ?? 60)
        setRetryAt(Date.now() + seconds * 1000)
        error.message = `请求额度暂不可用，请至少等待 ${seconds} 秒后用原请求重试。`
      }
      throw error
    } finally { setBusy(false) }
  }
  return { controller, submit, busy: busy || retryAt > Date.now() }
}

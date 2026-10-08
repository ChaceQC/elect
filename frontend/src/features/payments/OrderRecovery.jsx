import { useRef, useState } from 'react'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from '../auth/SessionProvider.jsx'

/** @typedef {import('../../api/generated').components['schemas']['Order']} Order */
/** @param {{order: Order, onChange: (order: Order)=>Promise<unknown>, onRefresh: ()=>Promise<unknown>}} props */
export function OrderRecovery({ order, onChange, onRefresh }) {
  const { profile } = useSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const writing = useRef(false)
  async function resume() {
    if (writing.current || !profile) return
    writing.current = true; setBusy(true); setError('')
    try {
      const result = await apiClient.request(`/payment-orders/${order.order_id}/resume-check`, {
        method: 'POST', body: { expected_version: order.version } })
      await onChange(/** @type {Order} */ (result.data))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '恢复结果尚未确认，请稍后重试。')
      await onRefresh()
    } finally { writing.current = false; setBusy(false) }
  }
  return <div>
    <p>自动核对已达到时限并暂停，原订单仍保留，学校支付结果尚未确认。</p>
    {error && <StatusBlock title={error} error />}
    <button disabled={busy || !profile} onClick={() => { void resume() }}>
      {busy ? '正在恢复核对…' : '继续核对原订单'}
    </button>
  </div>
}

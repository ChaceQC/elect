import { useRef, useState } from 'react'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'

/** @typedef {import('../../api/generated').components['schemas']['Order']} Order */
/** @param {{order: Order, onChange: (order: Order)=>void}} props */
export function OrderCancellation({ order, onChange }) {
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const writing = useRef(false)
  async function cancel() {
    if (writing.current) return
    writing.current = true; setBusy(true); setError('')
    try {
      const result = await apiClient.request(`/payment-orders/${order.order_id}/cancel`, {
        method: 'POST', body: { expected_version: order.version } })
      onChange(/** @type {Order} */ (result.data)); setConfirm(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '取消结果未确认，请查询原订单。') }
    finally { writing.current = false; setBusy(false) }
  }
  return <div>
    {error && <StatusBlock title={error} error><p>请先查询最新支付结果，再决定是否取消。</p></StatusBlock>}
    {confirm ? <><p>取消会停止本系统继续处理此订单，完成后可以重新建单。学校二维码可能仍有效，请勿继续扫描旧二维码；取消不会退款。</p>
      <button disabled={busy} onClick={() => { void cancel() }}>{busy ? '正在取消…' : '确认取消支付'}</button>
      <button className="quiet" disabled={busy} onClick={() => setConfirm(false)}>保留原订单</button></>
      : <button className="quiet" onClick={() => setConfirm(true)}>取消支付</button>}
  </div>
}

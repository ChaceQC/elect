import { useState } from 'react'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { ApiError } from '../../api/client.js'

/** @param {{onAccepted: (id: string)=>void}} props */
export function BindingRecovery({ onAccepted }) {
  const { controller, submit, busy } = useRequestIntent()
  const [error, setError] = useState('')
  const pending = controller?.restore().filter(item => item.path === '/room-bindings' && !item.id) ?? []
  /** @param {import('../../api/intents.js').Intent} intent */
  async function retry(intent) {
    setError('')
    try { const value = await submit(intent); if (value.id) onAccepted(value.id) }
    catch (cause) {
      if (cause instanceof ApiError && cause.existingOperationId) onAccepted(cause.existingOperationId)
      else setError(cause instanceof ApiError ? cause.message : '受理仍未确认，请稍后查询。')
      if (cause instanceof ApiError && [400, 403, 404, 409, 422].includes(cause.status)) controller?.forget(intent.key)
    }
  }
  return <>{pending.map(intent => <StatusBlock key={intent.key} title="有一笔学校绑定受理尚未确认">
    <p>可用原候选和原幂等键查询受理；已受理操作会返回原编号。</p>
    <button disabled={busy} onClick={() => { void retry(intent) }}>重试原受理请求</button>
  </StatusBlock>)}{error && <StatusBlock title={error} error />}</>
}

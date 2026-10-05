import { useState } from 'react'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { ApiError } from '../../api/client.js'
import { isFeatureRejected } from '../../api/intents.js'

/** @param {{onAccepted: (id: string)=>void}} props */
export function BindingRecovery({ onAccepted }) {
  const { controller, submit, busy } = useRequestIntent()
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const pending = controller?.restore().filter(item => (item.path === '/room-bindings' || item.method === 'DELETE') && !item.id) ?? []
  /** @param {import('../../api/intents.js').Intent} intent */
  async function retry(intent) {
    setError(''); setNotice('')
    try { const value = await submit(intent); if (value.id) onAccepted(value.id) }
    catch (cause) {
      if (cause instanceof ApiError && cause.existingOperationId) onAccepted(cause.existingOperationId)
      else setError(cause instanceof ApiError ? cause.message : '受理仍未确认，请稍后查询。')
      if (isFeatureRejected(cause) || cause instanceof ApiError && [400, 403, 404, 409, 422].includes(cause.status)) controller?.forget(intent.key)
    }
  }
  return <>{pending.map(intent => <StatusBlock key={intent.key} title={intent.method === 'DELETE' ? '有一笔删除绑定受理尚未确认' : '有一笔学校绑定受理尚未确认'}>
    <p>将继续确认上次提交的结果；已经受理的操作会继续使用原记录。</p>
    <button disabled={busy} onClick={() => { void retry(intent) }}>查看上次提交结果</button>
    <button className="quiet" disabled={busy} onClick={() => {
      controller?.forget(intent.key); setError('')
      setNotice('已停止本地重试；学校请求仍可能已受理，请同步学校绑定核对。')
    }}>停止本地重试</button>
  </StatusBlock>)}{error && <StatusBlock title={error} error />}{notice && <StatusBlock title={notice} />}</>
}

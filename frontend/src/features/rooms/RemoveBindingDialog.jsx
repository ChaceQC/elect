import { useRef, useState } from 'react'
import { ApiError } from '../../api/client.js'
import { isFeatureRejected } from '../../api/intents.js'
import { Modal } from '../../components/Modal.jsx'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'

/** @param {{binding: import('../../api/generated').components['schemas']['Binding'], isDefault: boolean,
 * onClose: ()=>void, onAccepted: (id: string)=>void}} props */
export function RemoveBindingDialog({ binding, isDefault, onClose, onAccepted }) {
  const { controller, submit, busy } = useRequestIntent()
  const [confirmed, setConfirmed] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const intent = useRef(/** @type {import('../../api/intents.js').Intent|null} */ (null))
  async function remove() {
    if (!controller || submitting.current || !confirmed) return
    submitting.current = true; setError('')
    try {
      intent.current ??= controller.create(`/room-bindings/${binding.id}`, {}, 'operation', 'DELETE')
      const value = await submit(intent.current)
      if (value.id) onAccepted(value.id)
      onClose()
    } catch (cause) {
      if (cause instanceof ApiError && cause.existingOperationId) {
        onAccepted(cause.existingOperationId); onClose()
      } else setError(cause instanceof Error ? cause.message : '删除受理尚未确认，请查询原操作。')
      if ((isFeatureRejected(cause) || cause instanceof ApiError && [400, 403, 404, 409, 422].includes(cause.status)) && intent.current) {
        controller.forget(intent.current.key); intent.current = null
      }
    } finally { submitting.current = false }
  }
  return <Modal open title="删除学校绑定" onClose={onClose}>
    <p>将解除 <strong>{binding.display_name}</strong> 在学校的绑定关系。已采集历史会保留。</p>
    {isDefault && <StatusBlock title="这是当前默认寝室"><p>默认会在学校解绑确认后清空。监控先暂停旧目标，等待你重新选择默认寝室；确认期间仍可关闭监控。</p></StatusBlock>}
    <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />我确认解除该寝室的学校绑定</label>
    {error && <StatusBlock title={error} error />}
    <button disabled={!confirmed || busy} onClick={() => { void remove() }}>{busy ? '正在受理…' : intent.current ? '重试原删除请求' : '确认删除绑定'}</button>
  </Modal>
}

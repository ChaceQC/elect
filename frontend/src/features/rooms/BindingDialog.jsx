import { useRef, useState } from 'react'
import { ApiError } from '../../api/client.js'
import { Modal } from '../../components/Modal.jsx'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { useNow } from '../../hooks/useNow.js'

/** @param {{candidate: import('./CandidateSearch.jsx').Candidate, onClose: ()=>void,
 * onAccepted: (id: string)=>void}} props */
export function BindingDialog({ candidate, onClose, onAccepted }) {
  const { controller, submit, busy } = useRequestIntent()
  const intent = useRef(/** @type {import('../../api/intents.js').Intent|null} */ (null))
  const submitting = useRef(false)
  const [error, setError] = useState('')
  const now = useNow()
  async function bind() {
    if (!controller || submitting.current) return
    submitting.current = true; setError('')
    try {
      intent.current ??= controller.create('/room-bindings', { candidate_id: candidate.candidate_id })
      const accepted = await submit(intent.current)
      if (accepted.id) onAccepted(accepted.id)
      onClose()
    } catch (cause) {
      if (cause instanceof ApiError && cause.existingOperationId) {
        onAccepted(cause.existingOperationId); onClose()
      } else setError(cause instanceof ApiError ? cause.message : '受理结果未确认，请重试原请求或查看操作进度。')
      if (cause instanceof ApiError && [400, 403, 404, 409, 422].includes(cause.status) && intent.current) {
        controller.forget(intent.current.key); intent.current = null
      }
    } finally { submitting.current = false }
  }
  const expired = Date.parse(candidate.expires_at) <= now
  return <Modal open title="确认新增学校绑定" onClose={onClose}>
    <p>将绑定 <strong>{candidate.display_name}</strong>。</p>
    <p>已有默认寝室时会保留原默认；首次绑定在学校确认后自动设置默认。</p>
    {expired && !intent.current && <StatusBlock title="候选已过期，请关闭后重新核对" error />}
    {error && <StatusBlock title={error} error />}
    <button disabled={busy || expired && !intent.current} onClick={() => { void bind() }}>{busy ? '正在受理…' : intent.current ? '重试原受理请求' : '确认绑定'}</button>
  </Modal>
}

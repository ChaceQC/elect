import { useEffect, useRef, useState } from 'react'
import { Modal } from '../../components/Modal.jsx'

/** @param {{open: boolean, agreement: import('../../api/generated').components['schemas']['Agreement'],
 * onClose: ()=>void, onRead: ()=>void}} props */
export function AgreementDialog({ open, agreement, onClose, onRead }) {
  const content = useRef(/** @type {HTMLDivElement|null} */ (null))
  const [read, setRead] = useState(false)
  useEffect(() => {
    setRead(false)
    if (!open) return
    const frame = requestAnimationFrame(() => {
      const element = content.current
      if (element && element.scrollHeight <= element.clientHeight + 2) setRead(true)
    })
    return () => cancelAnimationFrame(frame)
  }, [open, agreement.version, agreement.content_hash])
  return <Modal open={open} title="应用使用协议" onClose={onClose}>
    <p className="muted">版本 {agreement.version}</p>
    <div ref={content} className="agreement-content" tabIndex={0} onScroll={(event) => {
      const element = event.currentTarget
      if (element.scrollTop + element.clientHeight >= element.scrollHeight - 4) setRead(true)
    }}>{agreement.content}</div>
    <p className="muted">{read ? '已到达协议末尾，请确认。' : '请阅读至末尾后确认。'}</p>
    <button disabled={!read} onClick={() => { onRead(); onClose() }}>我已阅读</button>
  </Modal>
}

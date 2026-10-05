import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'

/** @param {{open: boolean, title: string, onClose: ()=>void, children: import('react').ReactNode, inactive?: boolean}} props */
export function Modal({ open, title, onClose, children, inactive = false }) {
  const dialog = useRef(/** @type {HTMLDialogElement|null} */ (null))
  const titleId = useId()
  useEffect(() => {
    if (!open || !dialog.current) return
    const previous = document.activeElement
    const element = dialog.current
    element.showModal()
    element.querySelector('button')?.focus()
    return () => { element.close(); if (previous instanceof HTMLElement) previous.focus() }
  }, [open])
  return open && <dialog ref={dialog} className="modal" aria-labelledby={titleId} inert={inactive} aria-hidden={inactive || undefined}
    onCancel={(event) => { event.preventDefault(); onClose() }}
    onKeyDown={(event) => {
      if (event.key !== 'Tab') return
      const items = /** @type {NodeListOf<HTMLElement>} */ (event.currentTarget.querySelectorAll(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]'))
      const first = items[0], last = items[items.length - 1]
      if (!first) return
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }}
    onClick={(event) => {
      if (event.target !== event.currentTarget) return
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) onClose()
    }}>
    <div className="modal-content"><header><h2 id={titleId}>{title}</h2>
      <button className="icon-button" aria-label="关闭弹窗" onClick={onClose}><X size={20} /></button></header>{children}</div>
  </dialog>
}

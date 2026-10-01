import { useState } from 'react'
import { PaymentDialog } from './PaymentDialog.jsx'

/** @param {{bindingId: string, displayName: string, disabled?: boolean}} props */
export function PaymentEntry({ bindingId, displayName, disabled = false }) {
  const [target, setTarget] = useState(/** @type {{id: string, name: string}|null} */ (null))
  return <><button className="quiet" disabled={disabled} onClick={() => setTarget({ id: bindingId, name: displayName })}>充值电费</button>
    {target && <PaymentDialog key={target.id} bindingId={target.id} displayName={target.name} onClose={() => setTarget(null)} />}</>
}

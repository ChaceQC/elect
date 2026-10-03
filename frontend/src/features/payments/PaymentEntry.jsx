import { useState } from 'react'
import { PaymentDialog } from './PaymentDialog.jsx'
import { CreditCard } from 'lucide-react'

/** @param {{bindingId: string, displayName: string, disabled?: boolean, compact?: boolean}} props */
export function PaymentEntry({ bindingId, displayName, disabled = false, compact = false }) {
  const [target, setTarget] = useState(/** @type {{id: string, name: string}|null} */ (null))
  return <><button className={compact ? 'text-button' : 'primary'} aria-label="充值电费" disabled={disabled} onClick={() => setTarget({ id: bindingId, name: displayName })}><CreditCard size={compact ? 14 : 17} aria-hidden="true" />电费缴费</button>
    {target && <PaymentDialog key={target.id} bindingId={target.id} displayName={target.name} onClose={() => setTarget(null)} />}</>
}

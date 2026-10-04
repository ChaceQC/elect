import { useState } from 'react'
import { PaymentDialog } from './PaymentDialog.jsx'
import { CreditCard } from 'lucide-react'
import { usePaymentCapability } from './usePaymentCapability.js'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'

/** @param {{bindingId: string, displayName: string, disabled?: boolean, compact?: boolean}} props */
export function PaymentEntry({ bindingId, displayName, disabled = false, compact = false }) {
  const [target, setTarget] = useState(/** @type {{id: string, name: string}|null} */ (null))
  const capability = usePaymentCapability(bindingId)
  const { controller } = useRequestIntent()
  const recovery = !!capability.data?.unresolved_order || controller?.restore().some(item => item.kind === 'order' && item.body.binding_id === bindingId)
  const available = capability.data?.enabled
  return <><span className="payment-entry"><button className={compact ? 'text-button' : 'primary'} aria-label={recovery ? '查看原充值订单' : '充值电费'} disabled={disabled || !available && !recovery} onClick={() => setTarget({ id: bindingId, name: displayName })}><CreditCard size={compact ? 14 : 17} aria-hidden="true" />{recovery ? '查看原订单' : capability.isPending ? '正在检查缴费…' : available ? '电费缴费' : '缴费暂不可用'}</button>
    {!available && <small className="field-hint">{capability.error ? '暂时无法确认缴费是否开放' : capability.data?.unavailable_reason}</small>}
    {capability.error && <button className="text-button" onClick={() => { void capability.refetch() }}>重新检查缴费</button>}</span>
    {target && <PaymentDialog key={target.id} bindingId={target.id} displayName={target.name} onClose={() => setTarget(null)} />}</>
}

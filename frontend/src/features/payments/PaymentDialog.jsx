import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Decimal from 'decimal.js'
import { ApiError, apiClient } from '../../api/client.js'
import { isFeatureRejected } from '../../api/intents.js'
import { Modal } from '../../components/Modal.jsx'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { validateAmount } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { OrderStatus } from './OrderStatus.jsx'

/** @param {{bindingId: string, displayName: string, onClose: ()=>void}} props */
export function PaymentDialog({ bindingId, displayName, onClose }) {
  const { user } = useSession()
  const { controller, submit, busy } = useRequestIntent()
  const [amount, setAmount] = useState('1')
  const [orderId, setOrderId] = useState(/** @type {string|null} */ (null))
  const [frozen, setFrozen] = useState(/** @type {import('../../api/intents.js').Intent|null} */ (null))
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const capability = useQuery({ queryKey: ['payment-capabilities', user?.id, bindingId], retry: false,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Capabilities']} */ (
      (await apiClient.request(`/payments/capabilities?binding_id=${bindingId}`, { signal })).data) })
  const rules = capability.data
  const restored = controller?.restore().find(item => item.kind === 'order' && item.path === '/payment-orders' && item.body.binding_id === bindingId)
  const intent = frozen ?? restored
  const id = orderId ?? rules?.unresolved_order?.order_id ?? intent?.id ?? null
  useEffect(() => { if (id && !orderId) setOrderId(id) }, [id, orderId])
  const normalized = /^\d+(?:\.\d{1,2})?$/.test(amount) ? new Decimal(amount).toFixed(2) : ''
  const limits = rules ? { minimum: rules.min_amount, maximum: rules.max_amount, step: rules.amount_step } : null
  const valid = !!limits && validateAmount(normalized, limits)
  async function create() {
    if (!controller || submitting.current || id || !intent && (!valid || !rules?.enabled)) return
    submitting.current = true; setError('')
    const request = intent ?? controller.create('/payment-orders', { binding_id: bindingId, amount: normalized }, 'order')
    setFrozen(request)
    try {
      const accepted = await submit(request)
      setOrderId(accepted.id)
    } catch (cause) {
      if (cause instanceof ApiError && cause.existingOperationId) setOrderId(cause.existingOperationId)
      else setError(cause instanceof ApiError ? cause.message : '订单受理未确认，请保留原请求并查询。')
      if (isFeatureRejected(cause) || cause instanceof ApiError && [400, 403, 404, 422].includes(cause.status)) {
        controller.forget(request.key); setFrozen(null)
      }
      void capability.refetch()
    } finally { submitting.current = false }
  }
  return <Modal open title="充值电费" onClose={onClose}>
    <p>充值寝室：<strong>{displayName}</strong></p>
    {capability.isPending && <StatusBlock title="正在读取支付规则与原订单…" />}
    {capability.error && <StatusBlock title={capability.error.message} error action={{ label: '重新读取支付规则', onClick: () => { void capability.refetch() } }} />}
    {rules && !rules.enabled && <StatusBlock title={rules.unavailable_reason ?? '支付暂未开放'} />}
    {id ? <OrderStatus key={id} id={id} onStartNew={() => {
      void capability.refetch().then(() => { setOrderId(null); setFrozen(null); setAmount('1') })
    }} /> : <>
      {rules && <p className="muted">{rules.currency} · {rules.min_amount}–{rules.max_amount}元，步长{rules.amount_step}元 · 应用充值规则</p>}
      <label className="payment-amount">充值金额（元）<input inputMode="decimal" maxLength={16}
        value={intent ? String(intent.body.amount) : amount} disabled={busy || !!intent || !rules?.enabled}
        onChange={event => setAmount(event.target.value)} /></label>
      {rules?.enabled && !intent && <div className="payment-presets">{['1.00', '10.00', '20.00', '50.00', '100.00'].filter(value => limits && validateAmount(value, limits))
        .map(value => <button className="quiet" key={value} onClick={() => setAmount(value)}>{new Decimal(value).toFixed(0)}元</button>)}</div>}
      {rules?.enabled && !intent && !valid && <p role="alert">请按当前金额范围和步长输入充值金额。</p>}
      {intent && <p role="status">原订单受理结果待确认，寝室和金额已固定；再次提交会保留原请求。</p>}
      {error && <StatusBlock title={error} error />}
      <button disabled={busy || capability.isPending || !intent && (!rules?.enabled || !valid)} onClick={() => { void create() }}>
        {busy ? '正在受理…' : intent ? '重试原订单请求' : '确认创建充值订单'}</button>
    </>}
    <p className="muted">关闭弹窗会保留订单。建单和二维码生成不代表已付款，到账余额以学校最新查询为准。</p>
  </Modal>
}

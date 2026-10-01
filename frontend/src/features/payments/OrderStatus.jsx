import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { isTerminal, pollInterval } from '../../api/operations.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { PaymentQr } from './PaymentQr.jsx'

const labels = { created: '订单已受理', submitting: '学校建单处理中', awaiting_payment: '等待付款',
  submit_unknown: '建单结果尚未确认', status_unknown: '支付状态尚未确认', paid_confirmed: '学校已确认支付',
  rejected: '学校建单已拒绝', expired_confirmed: '学校已确认订单过期', closed_confirmed: '学校已确认订单关闭' }

/** @param {{id: string}} props */
export function OrderStatus({ id }) {
  const { user } = useSession()
  const cache = useQueryClient()
  const { controller } = useRequestIntent()
  const started = useRef(Date.now())
  const query = useQuery({ queryKey: ['payment-order', user?.id, id], retry: false,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Order']} */ (
      (await apiClient.request(`/payment-orders/${id}`, { signal })).data),
    refetchInterval: query => pollInterval('order', query.state.data?.state === 'paid_confirmed' && query.state.data.balance_refresh_state === 'pending'
      ? 'awaiting_payment' : query.state.data?.state, Date.now() - started.current, document.visibilityState !== 'hidden'),
    refetchIntervalInBackground: false })
  const order = query.data
  useEffect(() => {
    if (!order || !isTerminal('order', order.state)) return
    for (const intent of controller?.restore() ?? []) if (intent.kind === 'order' && intent.id === id) controller?.forget(intent.key)
    void cache.invalidateQueries({ queryKey: ['payment-capabilities', user?.id, order.binding_id] })
    if (order.paid_confirmed) {
      for (const prefix of ['balance', 'overview', 'bindings', 'binding-view']) void cache.invalidateQueries({ queryKey: [prefix, user?.id] })
    }
  }, [order, controller, cache, user?.id, id])
  return <section className="payment-order" aria-live="polite">
    {query.isPending && <StatusBlock title="正在读取原订单…" />}
    {query.error && <StatusBlock title={query.error.message} error />}
    {order && <><h3>{labels[order.state]}</h3><p>{order.binding_display_name} · <strong>{moneyLabel(order.amount)}</strong></p>
      <p className="muted">订单参考：{order.order_id}</p>
      {['submit_unknown', 'status_unknown'].includes(order.state) && <p>学校结果尚未确认，请查询此订单；当前寝室的原订单仍被保留。</p>}
      {order.error_code && <p role="alert">最近查询未完成（{order.error_code}）。</p>}
      {order.state === 'paid_confirmed' && <p>{order.balance_refresh_state === 'succeeded' ? '学校余额已重新查询，到账以查询结果为准。'
        : order.balance_refresh_state === 'failed' ? '支付已确认，余额刷新失败；请在寝室页面重新查询余额。' : '支付已确认，正在重新查询学校余额。'}</p>}
      {!isTerminal('order', order.state) && <PaymentQr order={order} onRefresh={() => { void query.refetch() }} />}
      {order.last_checked_at && <p className="muted">学校结果最近查询：{new Date(order.last_checked_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p>}
    </>}
    <button className="quiet" disabled={query.isFetching} onClick={() => { void query.refetch() }}>查询支付结果</button>
  </section>
}

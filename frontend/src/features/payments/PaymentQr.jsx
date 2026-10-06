import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { useSession } from '../auth/SessionProvider.jsx'

/** @param {{order: import('../../api/generated').components['schemas']['Order'], onRefresh: ()=>void}} props */
export function PaymentQr({ order, onRefresh }) {
  const { user, profile } = useSession()
  const { controller, submit, busy, coolingDown } = useRequestIntent()
  const [image, setImage] = useState('')
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const query = useQuery({ queryKey: ['payment-qr', user?.id, order.order_id, order.qr_status], retry: false,
    enabled: ['generating', 'ready'].includes(order.qr_status),
    queryFn: async ({ signal }) => apiClient.request(`/payment-orders/${order.order_id}/qr`, { signal, responseType: 'image' }),
    refetchInterval: query => query.state.data?.status === 202 && !['unknown', 'failed'].includes(query.state.data.data?.qr_status) ? 5000 : false,
    refetchIntervalInBackground: false })
  useEffect(() => {
    if (query.data?.status !== 200) { setImage(''); return }
    const url = URL.createObjectURL(query.data.data)
    setImage(url)
    return () => URL.revokeObjectURL(url)
  }, [query.data])
  async function refresh() {
    if (!profile || !controller || submitting.current || coolingDown) return
    submitting.current = true; setError('')
    const path = `/payment-orders/${order.order_id}/qr-refresh`
    const previous = controller.restore().find(item => item.path === path && !item.id)
    try {
      const accepted = await submit(previous ?? controller.create(path))
      // 服务端订单摘要负责恢复；该刷新受理编号不产生第二个订单。
      controller.forget(accepted.key)
      await query.refetch(); onRefresh()
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : '二维码请求受理未确认，请保留原订单。') }
    finally { submitting.current = false }
  }
  return <div className="payment-qr">
    {image ? <img src={image} width={220} height={220} alt="此充值订单的微信支付二维码" onError={() => setError('二维码图片显示失败，请重新读取原订单图片。')} />
      : <p>{order.qr_status === 'unknown' ? '支付页面结果尚未确认，暂无法展示二维码。' : order.qr_status === 'failed' ? '二维码获取失败，原订单仍保留。'
        : order.qr_status === 'not_requested' ? '订单确认后生成二维码。' : '正在取得原订单二维码…'}</p>}
    {image && <p className="muted">二维码有效期尚未确认。扫码后支付结果会自动更新。</p>}
    {(query.error || error) && <StatusBlock title={error || query.error?.message || '二维码读取失败'} error />}
    {order.qr_error_code && <p className="muted">二维码状态：{order.qr_error_code}</p>}
    {['awaiting_payment', 'status_unknown'].includes(order.state) && order.qr_status !== 'unknown' && <button className="quiet" disabled={!profile || busy || coolingDown} onClick={() => { void refresh() }}>重新获取同订单二维码</button>}
  </div>
}

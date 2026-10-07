import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, Wallet } from 'lucide-react'
import Decimal from 'decimal.js'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { serverNow, timestampLabel } from '../../lib/dates.js'
import { isBalanceStale } from '../../lib/balance.js'
import { useNow } from '../../hooks/useNow.js'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { PaymentEntry } from '../payments/PaymentEntry.jsx'
import { QueryAction } from './QueryAction.jsx'

/** @param {{bindingId: string, displayName?: string, variant?: 'overview'|'details', isDefault?: boolean, threshold?: string}} props */
export function BalancePanel({ bindingId, displayName, variant = 'details', isDefault = false, threshold }) {
  const { user } = useSession()
  const query = useQuery({ queryKey: ['balance', user?.id, bindingId], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Balance']} */ ((await apiClient.request(`/room-bindings/${bindingId}/balance`, { signal })).data) })
  const balance = query.data
  const stale = isBalanceStale(balance, serverNow(useNow()))
  const low = balance?.amount != null && threshold != null && new Decimal(balance.amount).lt(threshold)
  const overview = variant === 'overview'
  return <section className={overview ? 'balance-card' : 'card details-balance'} aria-label="当前寝室余额">
    <div className="balance-main"><div className="card-heading"><span className="balance-title">{overview && <Wallet size={18} aria-hidden="true" />}{overview ? '当前电费余额' : `${displayName ?? '当前寝室'} · 电费余额`}</span>
      {overview && balance && <span className="light-pill">{balance.amount == null ? '余额未知' : stale ? '待更新' : low ? '余额偏低' : threshold ? '余额充足' : '最近余额'}</span>}</div>
      {query.isPending && <p role="status">正在读取最近成功余额…</p>}
      {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取缓存', onClick: () => { void query.refetch() } }} />}
      {balance && <><strong className="balance-amount">{balance.amount == null ? '—' : <><small>¥</small>{moneyLabel(balance.amount).replace('¥', '')}</>}</strong>
        {overview && <p className="balance-room">{displayName}<span>{isDefault ? '默认寝室' : '独立查看'}</span></p>}
        {balance.amount === null && <p className="balance-warning">尚未取得有效余额，请刷新查询</p>}
        {stale && <p className="balance-warning">余额已过期，请刷新确认</p>}
        {low && <p className="balance-warning" role="status">最近余额低于已设置阈值{threshold}元{stale ? '，余额已过期，请刷新确认' : ''}。</p>}
        {balance.error_code && <p className="balance-warning" role="alert">最近刷新失败：{balance.error_code}，保留上次成功值。</p>}</>}
    </div>
    <div className="balance-bottom"><span>最近更新 · {timestampLabel(balance?.fetched_at ?? null)}</span><div className="actions">
      <QueryAction compact autoRefresh path={`/room-bindings/${bindingId}/balance-refresh`} label="刷新学校余额" />
      {overview ? <><PaymentEntry compact bindingId={bindingId} displayName={displayName ?? '所选寝室'} /><Link to={`/details?binding_id=${bindingId}`}>查看明细 <ArrowRight size={16} aria-hidden="true" /></Link></> :
        displayName && <PaymentEntry bindingId={bindingId} displayName={displayName} />}
    </div></div>
  </section>
}

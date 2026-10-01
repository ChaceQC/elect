import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { timestampLabel } from '../../lib/dates.js'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { QueryAction } from './QueryAction.jsx'

/** @param {{bindingId: string}} props */
export function BalancePanel({ bindingId }) {
  const { user } = useSession()
  const query = useQuery({ queryKey: ['balance', user?.id, bindingId], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Balance']} */ ((await apiClient.request(`/room-bindings/${bindingId}/balance`, { signal })).data) })
  const balance = query.data
  return <section className="data-card balance-panel"><h2>当前寝室余额</h2>
    {query.isPending && <p role="status">正在读取最近成功余额…</p>}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取缓存', onClick: () => { void query.refetch() } }} />}
    {balance && <><strong className="balance-amount">{balance.amount == null ? '未知' : moneyLabel(balance.amount)}</strong>
      <p>{balance.amount === null ? '尚未取得有效余额，请刷新查询' : balance.stale ? '余额已过期，请刷新确认' : '最近成功取得的学校余额'}</p>
      <p className="muted">学校查询时间：{timestampLabel(balance.fetched_at)}</p>
      {balance.error_code && <p role="alert">最近刷新失败：{balance.error_code}，保留上次成功值。</p>}</>}
    <QueryAction path={`/room-bindings/${bindingId}/balance-refresh`} label="刷新学校余额" />
  </section>
}

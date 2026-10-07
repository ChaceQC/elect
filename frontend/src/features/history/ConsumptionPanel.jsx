import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { ConsumptionTrend } from './LazyTrend.jsx'
import { QueryAction } from './QueryAction.jsx'

/** @param {{bindingId: string, range: import('./DateRangePicker.jsx').Range, granularity: 'day'|'week'|'month', onGranularity: (value: string)=>void}} props */
export function ConsumptionPanel({ bindingId, range, granularity, onGranularity }) {
  const { user } = useSession()
  const query = useQuery({ queryKey: ['consumption', user?.id, bindingId, range, granularity], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Consumption']} */ ((await apiClient.request(`/room-bindings/${bindingId}/consumption?${new URLSearchParams({ ...range, granularity })}`, { signal })).data),
    refetchInterval: data => data.state.data?.sync_status === 'loading' ? 2000 : 60_000,
    refetchIntervalInBackground: false })
  const history = query.data
  return <section className="card"><div className="card-heading"><div><h2>历史消费趋势</h2>
    {history && !history.summary.complete && <p className="history-summary">已知合计 {moneyLabel(history.summary.amount)} · {history.summary.known_days}/{history.summary.expected_days} 天（数据不完整{history.summary.estimated_amount != null ? '，含余额变化估算' : ''}）</p>}</div>
    <div className="actions"><QueryAction compact key={bindingId} path={`/room-bindings/${bindingId}/history-sync`} body={range} label="同步所选范围的学校历史" operationId={history?.sync_operation && ['accepted', 'running'].includes(history.sync_operation.state) ? history.sync_operation.id : undefined} />
    <div className="segments" role="group" aria-label="图表粒度">{[['month', '月'], ['week', '周'], ['day', '天']].map(([value, label]) => <button key={value} className={granularity === value ? 'selected' : ''} aria-pressed={granularity === value} onClick={() => onGranularity(value)}>{label}</button>)}</div></div></div>
    {query.isPending && <p role="status">正在读取消费趋势…</p>}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取历史', onClick: () => { void query.refetch() } }} />}
    {history && <>
      {history.sync_status === 'stale' && <p role="alert">最近同步失败，正在展示已有历史。</p>}
      {history.sync_status === 'failed' && <p role="alert">学校历史同步失败，请稍后重试；已有采集估算仍可展示。</p>}
      {history.monitoring_status === 'unavailable' && <p role="alert">监控估算暂时不可用，正在展示已有学校历史。</p>}
      {history.buckets.some(b => b.amount !== null) ? <ConsumptionTrend buckets={history.buckets} /> : <p>所选范围暂无已知消费记录。</p>}</>}
  </section>
}

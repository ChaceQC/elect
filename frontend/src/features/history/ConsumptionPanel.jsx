import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { ConsumptionTrend } from './LazyTrend.jsx'
import { QueryAction } from './QueryAction.jsx'

/** @param {{bindingId: string, range: import('./DateRangePicker.jsx').Range, granularity: 'day'|'week'|'month'}} props */
export function ConsumptionPanel({ bindingId, range, granularity }) {
  const { user } = useSession()
  const query = useQuery({ queryKey: ['consumption', user?.id, bindingId, range, granularity], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Consumption']} */ ((await apiClient.request(`/room-bindings/${bindingId}/consumption?${new URLSearchParams({ ...range, granularity })}`, { signal })).data),
    refetchInterval: data => data.state.data?.sync_status === 'loading' ? 2000 : false })
  const history = query.data
  return <section className="data-card"><h2>学校消费记录</h2>
    <p className="muted">图表和采集明细使用同一日期范围。金额来自学校返回的扣费记录；缺失日期保留未知。</p>
    {query.isPending && <p role="status">正在读取学校消费历史…</p>}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取历史', onClick: () => { void query.refetch() } }} />}
    {history && <><p className="history-total">{history.summary.complete ? '消费合计' : '已知消费合计'}：<strong>{moneyLabel(history.summary.amount)}</strong></p>
      <p>已知 {history.summary.known_days}/{history.summary.expected_days} 天 · {history.coverage === 'complete' ? '覆盖完整' : history.coverage === 'partial' ? '部分数据，合计可能不完整' : '覆盖未知'}</p>
      {history.sync_status === 'stale' && <p role="alert">最近同步失败，正在展示已有历史。</p>}
      {history.sync_status === 'failed' && <p role="alert">学校历史同步失败，请稍后重试；暂无成功历史可展示。</p>}
      {history.buckets.some(b => b.amount !== null) ? <ConsumptionTrend buckets={history.buckets} /> : <p>所选范围暂无已知消费记录。</p>}</>}
    <QueryAction key={bindingId} path={`/room-bindings/${bindingId}/history-sync`} body={range} label="同步所选范围的学校历史" operationId={history?.sync_operation && ['accepted', 'running'].includes(history.sync_operation.state) ? history.sync_operation.id : undefined} />
  </section>
}

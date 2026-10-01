import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useParams } from 'react-router-dom'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { BalancePanel } from '../history/BalancePanel.jsx'

export function RoomView() {
  const { user } = useSession()
  const { bindingId } = useParams()
  const cache = useQueryClient()
  const query = useQuery({ queryKey: ['binding-view', user?.id, bindingId], enabled: !!user && !!bindingId,
    retry: false, queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Binding']} */ (
      (await apiClient.request(`/room-bindings/${bindingId}`, { signal })).data) })
  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 404) cache.removeQueries({ queryKey: ['binding-view', user?.id, bindingId] })
  }, [query.error, cache, user?.id, bindingId])
  if (query.error instanceof ApiError && query.error.status === 404) return <Navigate to="/rooms" replace state={{ roomUnavailable: true }} />
  const binding = query.data
  return <><p className="eyebrow">独立查看</p><h1>{binding?.display_name ?? '寝室详情'}</h1>
    <p className="page-description">查看此寝室不会修改默认寝室或监控目标。</p><Link to="/rooms">返回我的寝室</Link>
    {query.isPending && <StatusBlock title="正在读取寝室…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取', onClick: () => { void query.refetch() } }} />}
    {binding && <><BalancePanel key={binding.id} bindingId={binding.id} /><Link to={`/details?binding_id=${binding.id}`}>查看此寝室消费与采集明细</Link><section className="monitor-summary"><h2>绑定确认信息</h2>
      <strong>{binding.balance?.amount == null ? '未知' : moneyLabel(binding.balance.amount)}</strong>
      <p>{binding.balance?.stale ? '余额已过期' : '最近成功取得的学校余额'} · {binding.status === 'rechecking' ? '绑定关系待复核' : '学校已绑定'}</p>
      <p className="muted">学校查询时间：{binding.balance?.fetched_at ? new Date(binding.balance.fetched_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '暂无'}</p>
    </section></>}
  </>
}

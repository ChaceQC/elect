import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Bell, Home, Wallet, Zap } from 'lucide-react'
import { apiClient } from '../../api/client.js'
import { PageHeading } from '../../components/layout/PageHeading.jsx'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { useBindings } from '../rooms/useBindings.js'
import { BalancePanel } from './BalancePanel.jsx'
import { ConsumptionTrend } from './LazyTrend.jsx'
import { QueryAction } from './QueryAction.jsx'
import { FirstBindingGuide } from '../rooms/FirstBindingGuide.jsx'

export function OverviewPage() {
  const { user } = useSession()
  const bindings = useBindings({ pageSize: 100 })
  const [search, setSearch] = useSearchParams()
  const viewing = search.get('binding_id') ?? ''
  const query = useQuery({ queryKey: ['overview', user?.id, viewing, bindings.data?.default_binding_id], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Overview']} */ ((await apiClient.request(`/overview${viewing ? `?binding_id=${viewing}` : ''}`, { signal })).data),
    refetchInterval: 60_000, refetchIntervalInBackground: false })
  const control = useQuery({ queryKey: ['monitor', user?.id], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Monitor']} */ ((await apiClient.request('/monitor', { signal })).data) })
  const overview = query.data
  const bindingId = overview?.viewing_binding_id
  const room = bindings.data?.items.find(item => item.id === bindingId)
  if (!viewing && bindings.data?.sync_status === 'empty' && bindings.data.total === 0) return <FirstBindingGuide />
  return <><PageHeading title="总览">
    {(!!viewing || (bindings.data?.items.length ?? 0) > 1) && <label className="room-picker">查看寝室<select value={viewing} onChange={event => {
      const next = new URLSearchParams(search)
      event.target.value ? next.set('binding_id', event.target.value) : next.delete('binding_id')
      setSearch(next)
    }}><option value="">默认寝室</option>{bindings.data?.items.map(binding => <option key={binding.id} value={binding.id}>{binding.display_name}</option>)}</select></label>}
    </PageHeading>
    {viewing && <p className="muted room-view-note">独立查看不会改变默认寝室或监控目标。</p>}
    {query.isPending && <StatusBlock title="正在读取总览…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取总览', onClick: () => { void query.refetch() } }} />}
    {overview && <><div className="overview-top">
      {bindingId ? <BalancePanel key={bindingId} bindingId={bindingId} displayName={room?.display_name ?? '所选寝室'}
        variant="overview" isDefault={bindingId === bindings.data?.default_binding_id} threshold={control.data?.config.threshold} /> :
        <StatusBlock title="暂无有效默认寝室"><Link className="button-link" to="/rooms">管理我的寝室</Link></StatusBlock>}
      <section className="card user-card"><div className="card-heading"><h2>用户信息</h2><Home className="tiny-icon" size={19} aria-hidden="true" /></div>
        {overview.profile ? <dl><div><dt>学号</dt><dd>{overview.profile.student_id}</dd></div>
          <div><dt>默认寝室</dt><dd>{overview.profile.default_binding?.display_name ?? '未设置'}</dd></div>
          <div><dt>预警邮箱</dt><dd>{overview.profile.alert_email ?? <Link to="/monitor">尚未设置，去添加</Link>}</dd></div></dl> : <p>个人信息暂时不可用。</p>}
        {overview.component_status.profile === 'partial' && <p role="alert">部分个人信息暂时不可用。</p>}
      </section></div>
      <div className="stat-grid"><section className="card stat"><div className="stat-label"><span>昨日消费</span><Zap size={18} aria-hidden="true" /></div>
        <div className="stat-value">{moneyLabel(overview.summary?.yesterday_amount ?? null).replace('¥', '')}<small>元</small></div>
        {overview.summary?.yesterday_amount == null && <p className="muted">昨日完整消费尚未取得</p>}</section>
        <section className="card stat"><div className="stat-label"><span>近 14 天消费</span><Wallet size={18} aria-hidden="true" /></div>
          <div className="stat-value">{moneyLabel(overview.summary?.last_14_days_amount ?? null).replace('¥', '')}<small>元</small></div>
          {overview.summary && !overview.summary.complete && <p className="muted">已知{overview.summary.known_days}/{overview.summary.expected_days}天 · 部分数据，合计可能不完整{overview.daily_consumption?.summary.estimated_amount != null ? '，含余额变化估算' : ''}</p>}</section>
        <section className="card stat"><div className="stat-label"><Link to="/monitor">监控状态</Link><Bell size={18} aria-hidden="true" /></div>
          <div className="stat-value">{overview.monitor ? overview.monitor.enabled ? '已开启' : '未开启' : '—'}</div>
          {overview.monitor?.enabled && overview.monitor.health !== 'healthy' && <p className="muted">{overview.monitor.health === 'degraded' ? '采集部分异常' : '采集暂不可用'} · <Link to="/monitor">查看状态</Link></p>}</section></div>
      <section className="card overview-trend"><div className="card-heading"><h2>历史每日消费</h2><div className="actions"><span className="pill">最近 14 天</span>
        {bindingId && overview.daily_consumption && <QueryAction compact key={bindingId} path={`/room-bindings/${bindingId}/history-sync`} body={{ start_date: overview.daily_consumption.start_date, end_date: overview.daily_consumption.end_date }} label="同步最近14天学校历史" />}</div></div>
        {overview.daily_consumption?.buckets.some(b => b.amount !== null) ? <ConsumptionTrend buckets={overview.daily_consumption.buckets} /> : <div className="empty">暂无已知消费记录。</div>}
        {overview.daily_consumption?.monitoring_status === 'unavailable' && <p role="alert">监控估算暂时不可用，正在展示已有学校历史。</p>}
        {overview.component_status.history === 'failed' && <p role="alert">学校历史暂时不可用，余额和监控信息仍可独立读取。</p>}
      </section></>}
  </>
}

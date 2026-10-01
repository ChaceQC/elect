import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import Decimal from 'decimal.js'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { useBindings } from '../rooms/useBindings.js'
import { BalancePanel } from './BalancePanel.jsx'
import { ConsumptionTrend } from './LazyTrend.jsx'
import { QueryAction } from './QueryAction.jsx'

export function OverviewPage() {
  const { user } = useSession()
  const bindings = useBindings({ pageSize: 100 })
  const [search, setSearch] = useSearchParams()
  const viewing = search.get('binding_id') ?? ''
  const query = useQuery({ queryKey: ['overview', user?.id, viewing, bindings.data?.default_binding_id], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Overview']} */ ((await apiClient.request(`/overview${viewing ? `?binding_id=${viewing}` : ''}`, { signal })).data) })
  const control = useQuery({ queryKey: ['monitor', user?.id], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Monitor']} */ ((await apiClient.request('/monitor', { signal })).data) })
  const overview = query.data
  const bindingId = overview?.viewing_binding_id
  const low = overview?.balance?.amount != null && control.data && new Decimal(overview.balance.amount).lt(control.data.config.threshold)
  return <><p className="eyebrow">我的寝室生活</p><h1>用电总览</h1><p className="page-description">了解当前寝室余额和最近14天的学校消费记录。</p>
    {!!bindings.data?.items.length && <label className="room-picker">查看寝室<select value={viewing} onChange={event => {
      const next = new URLSearchParams(search)
      event.target.value ? next.set('binding_id', event.target.value) : next.delete('binding_id')
      setSearch(next)
    }}>
      <option value="">默认寝室</option>{bindings.data.items.map(binding => <option key={binding.id} value={binding.id}>{binding.display_name}</option>)}</select></label>}
    {viewing && <p className="muted">独立查看不会改变默认寝室或监控目标。</p>}
    {query.isPending && <StatusBlock title="正在读取总览…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取总览', onClick: () => { void query.refetch() } }} />}
    {overview && <><section className="data-card"><h2>我的信息</h2>
      {overview.profile ? <><p>学号：{overview.profile.student_id}</p><p>默认寝室：{overview.profile.default_binding?.display_name ?? '未设置'}</p><p>提醒邮箱：{overview.profile.alert_email ?? '未设置'}</p></> : <p>个人信息暂时不可用。</p>}
      {overview.component_status.profile === 'partial' && <p role="alert">部分个人信息暂时不可用。</p>}
    </section>
    {bindingId ? <BalancePanel key={bindingId} bindingId={bindingId} /> : <StatusBlock title="暂无有效默认寝室"><Link to="/rooms">管理我的寝室</Link></StatusBlock>}
    {low && <p className="low-balance" role="status">最近余额低于已设置阈值{control.data?.config.threshold}元{overview.balance?.stale ? '，余额已过期，请刷新确认' : ''}。</p>}
    <section className="data-card"><h2>最近14天</h2>
      {overview.summary ? <><p>完整昨日消费：{moneyLabel(overview.summary.yesterday_amount)}</p><p>已知消费合计：<strong>{moneyLabel(overview.summary.last_14_days_amount)}</strong></p>
        <p>已知{overview.summary.known_days}/{overview.summary.expected_days}天{overview.summary.complete ? '' : ' · 部分数据，合计可能不完整'}</p></> : <p>消费汇总暂时不可用。</p>}
      {overview.daily_consumption?.buckets.some(b => b.amount !== null) ? <ConsumptionTrend buckets={overview.daily_consumption.buckets} /> : <p>暂无已知学校消费记录。</p>}
      {overview.component_status.history === 'failed' && <p role="alert">学校历史暂时不可用，余额和监控信息仍可独立读取。</p>}
      {bindingId && overview.daily_consumption && <QueryAction key={bindingId} path={`/room-bindings/${bindingId}/history-sync`} body={{ start_date: overview.daily_consumption.start_date, end_date: overview.daily_consumption.end_date }} label="同步最近14天学校历史" />}
      <Link to={bindingId ? `/details?binding_id=${bindingId}` : '/details'}>查看电费明细</Link>
    </section>
    <section className="data-card"><h2>后台监控</h2><p>{overview.monitor ? `${overview.monitor.enabled ? '已启用' : '已关闭'} · ${overview.monitor.health === 'healthy' ? '采集正常' : overview.monitor.health === 'degraded' ? '采集部分异常' : '采集暂不可用'}` : '监控状态暂时不可用'}</p><Link to="/monitor">查看监控设置和运行</Link></section></>}
  </>
}

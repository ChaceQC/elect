import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { timestampLabel } from '../../lib/dates.js'
import { moneyLabel } from '../../lib/money.js'
import { randomId } from '../../lib/uuid.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { Clock3, RefreshCw } from 'lucide-react'

/** @param {{bindingId: string, range: import('./DateRangePicker.jsx').Range, page: number, onPageChange: (page: number)=>void}} props */
export function SamplesPanel({ bindingId, range, page, onPageChange }) {
  const { user } = useSession()
  const [snapshot, setSnapshot] = useState(/** @type {string|null} */ (null))
  const [revision, setRevision] = useState(() => randomId())
  const query = useQuery({ queryKey: ['samples', user?.id, bindingId, range, revision, page], enabled: !!user,
    queryFn: async ({ signal }) => {
      let token = snapshot
      const path = `/room-bindings/${bindingId}/monitor-samples`
      if (!token && page > 1) {
        const first = await apiClient.request(`${path}?${new URLSearchParams({ ...range, page: '1', page_size: '10' })}`, { signal })
        token = first.data.snapshot_token
      }
      return /** @type {import('../../api/generated').components['schemas']['Samples']} */ ((await apiClient.request(`${path}?${new URLSearchParams({ ...range, page: String(page), page_size: '10', ...(token ? { snapshot_token: token } : {}) })}`, { signal })).data)
    },
    staleTime: 60_000 })
  const samples = query.data
  const quality = { balance_only: '本次仅采集余额', meter_not_realtime: '学校日记录（非实时）', meter_inconsistent: '读数与学校用量不一致', meter_negative_delta: '读数差为负，请核对换表或回绕' }
  useEffect(() => { if (samples) setSnapshot(samples.snapshot_token) }, [samples])
  useEffect(() => { if (samples && page > Math.max(1, Math.ceil(samples.total / samples.page_size))) onPageChange(Math.max(1, Math.ceil(samples.total / samples.page_size))) }, [samples, page, onPageChange])
  function reset() { onPageChange(1); setSnapshot(null); setRevision(randomId()) }
  return <section className="card"><div className="card-heading"><h2>监控采集明细</h2><div className="actions">
    {samples && <span className="pill">{samples.total} 条</span>}<button className="icon-button" aria-label="读取最新采集记录" title="读取最新采集记录" onClick={reset}><RefreshCw size={16} /></button></div></div>
    {query.isPending && <p role="status">正在读取采集记录…</p>}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '从第一页重新读取', onClick: reset }} />}
    {samples && <>
      {!samples.items.length && <div className="empty"><Clock3 size={29} /><p>{samples.has_monitor_history ? '所选范围内暂无成功采集，历史记录会保留。' : '开启监控后开始积累采集记录。'}</p></div>}
      {!!samples.items.length && <div className="table-scroll" tabIndex={0} role="region" aria-label="监控采集数据表"><table className="samples-table"><caption className="sr-only">所选日期范围的成功采集</caption><thead><tr><th>采集时间</th><th>寝室余额</th><th><abbr title="本次余额减上次余额，包含充值等变化">余额变化</abbr></th><th>电表起码 / 止码 / 差值</th><th>读数来源与质量</th></tr></thead>
        <tbody>{samples.items.map(sample => <tr key={sample.id}><td>{timestampLabel(sample.captured_at)}{sample.gap_detected && <small>采集存在间隔</small>}</td><td>{moneyLabel(sample.balance)}</td><td>{moneyLabel(sample.balance_delta)}</td><td>{sample.meter_last_reading ?? '—'} / {sample.meter_reading ?? '—'} / {sample.meter_delta ?? '—'}</td>
          <td>{sample.meter_record_date && <small>{sample.meter_record_date} · 学校日记录</small>}{quality[sample.quality]}{sample.meter_is_repeated && <small>重复来源读数，不重复累计</small>}</td></tr>)}</tbody></table></div>}
      <div className="samples-footer"><p className="muted">共 {samples.total} 条</p><div className="pagination"><button className="quiet" disabled={page === 1 || query.isFetching} onClick={() => onPageChange(page - 1)}>上一页</button><span>第{page}页</span><button className="quiet" disabled={page * samples.page_size >= samples.total || query.isFetching || !snapshot} onClick={() => onPageChange(page + 1)}>下一页</button></div></div></>}
  </section>
}

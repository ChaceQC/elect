import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { addDays, selectableRange, shanghaiDate } from '../../lib/dates.js'
import { useBindings } from '../rooms/useBindings.js'
import { BalancePanel } from './BalancePanel.jsx'
import { ConsumptionPanel } from './ConsumptionPanel.jsx'
import { DateRangePicker } from './DateRangePicker.jsx'
import { SamplesPanel } from './SamplesPanel.jsx'
import { PaymentRecordsPanel } from './PaymentRecordsPanel.jsx'
import { PageHeading } from '../../components/layout/PageHeading.jsx'

export function HistoryPage() {
  const bindings = useBindings({ pageSize: 100 })
  const [search, setSearch] = useSearchParams()
  const bindingId = search.get('binding_id') || bindings.data?.default_binding_id
  const start = search.get('start_date') ?? '', end = search.get('end_date') ?? ''
  const validRange = selectableRange(start, end)
  const range = validRange ? { start_date: start, end_date: end } : { start_date: addDays(shanghaiDate(), -29), end_date: shanghaiDate() }
  const selected = search.get('granularity') ?? 'day'
  const granularity = /** @type {'day'|'week'|'month'} */ (['day', 'week', 'month'].includes(selected) ? selected : 'day')
  const requestedPage = Number(search.get('page') ?? '1')
  const page = Number.isSafeInteger(requestedPage) && requestedPage >= 1 ? requestedPage : 1
  useEffect(() => {
    const next = new URLSearchParams(search)
    if ((next.has('start_date') || next.has('end_date')) && !validRange) { next.delete('start_date'); next.delete('end_date'); next.delete('page') }
    if (selected !== granularity) next.delete('granularity')
    if (requestedPage !== page) next.delete('page')
    if (next.toString() !== search.toString()) setSearch(next, { replace: true })
  }, [search, setSearch, validRange, selected, granularity, requestedPage, page])
  /** @param {Record<string,string|null>} fields */
  function update(fields) {
    const next = new URLSearchParams(search)
    for (const [key, value] of Object.entries(fields)) value === null ? next.delete(key) : next.set(key, value)
    setSearch(next)
  }
  return <><PageHeading title="电费明细">
    {bindings.data && (bindings.data.items.length > 1 || !bindingId) && <label className="room-picker">查看寝室<select value={bindingId ?? ''} onChange={event => update({ binding_id: event.target.value || null, page: null })}>
      <option value="">选择寝室</option>{bindings.data.items.map(b => <option key={b.id} value={b.id}>{b.display_name}{b.id === bindings.data.default_binding_id ? '（默认）' : ''}</option>)}</select></label>}
    </PageHeading>
    {bindings.isPending && <StatusBlock title="正在读取寝室…" />}
    {bindings.error && <StatusBlock title={bindings.error.message} error action={{ label: '重新读取寝室', onClick: () => { void bindings.refetch() } }} />}
    {search.has('binding_id') && bindingId !== bindings.data?.default_binding_id && <p className="muted room-view-note">独立查看不会修改默认寝室或监控目标。</p>}
    {!bindingId && bindings.data && <StatusBlock title="请先选择或绑定寝室"><Link to="/rooms">管理我的寝室</Link></StatusBlock>}
    {bindingId && <><BalancePanel key={bindingId} bindingId={bindingId} displayName={bindings.data?.items.find(item => item.id === bindingId)?.display_name ?? '所选寝室'} /><DateRangePicker key={`${range.start_date}:${range.end_date}`} range={range} onApply={value => update({ ...value, page: null })} />
      <ConsumptionPanel bindingId={bindingId} range={range} granularity={granularity} onGranularity={value => update({ granularity: value })} />
      <SamplesPanel key={`${bindingId}:${range.start_date}:${range.end_date}`} bindingId={bindingId} range={range} page={page} onPageChange={value => update({ page: value === 1 ? null : String(value) })} />
      <PaymentRecordsPanel key={`payments:${bindingId}:${range.start_date}:${range.end_date}`} bindingId={bindingId} range={range} /></>}
  </>
}

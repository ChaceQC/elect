import { useState } from 'react'
import { ArrowRight, CalendarDays, Clock3 } from 'lucide-react'
import Trend from './Trend.jsx'
import DateRangePicker from './DateRangePicker.jsx'
import { aggregateHistory, DEMO_TODAY, filterHistory, monitorHistory, recentRange } from './historyData.js'
import './history.css'

const money = value => value.toFixed(2)
export default function DetailsHistory({ room, hasHistory, onMonitor }) {
  const [range, setRange] = useState(() => recentRange(30))
  const [draft, setDraft] = useState(range)
  const [preset, setPreset] = useState(30)
  const [period, setPeriod] = useState('day')
  const [page, setPage] = useState(1)
  const [error, setError] = useState('')
  const days = filterHistory(range)
  const points = aggregateHistory(days, period)
  const rows = hasHistory ? monitorHistory(room.balance, range) : []
  const totalPages = Math.max(1, Math.ceil(rows.length / 10))
  const rangeLabel = `${range.start} 至 ${range.end}`
  function apply(next, shortcut) {
    setRange(next); setDraft(next); setPreset(shortcut); setPage(1); setError('')
  }
  function submit(e) {
    e.preventDefault()
    if (!draft.start || !draft.end) return setError('请选择完整的开始和结束日期。')
    if (draft.start > draft.end) return setError('开始日期不能晚于结束日期。')
    if (draft.end > DEMO_TODAY) return setError('结束日期不能晚于演示日期。')
    apply(draft, 'custom')
  }
  return <>
    <section className="card history-range">
      <div className="card-heading"><h2><CalendarDays size={18} /> 时间范围</h2><div className="segments">{[7, 30, 90].map(days => <button key={days} aria-pressed={preset === days} className={preset === days ? 'selected' : ''} onClick={() => apply(recentRange(days), days)}>最近 {days} 天</button>)}</div></div>
      <form className="range-form" onSubmit={submit}>
        <DateRangePicker value={draft} onChange={next => { setDraft(next); setError('') }} />
        <button className="primary">应用范围</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      <p className="field-hint" aria-live="polite">{rangeLabel}{(draft.start !== range.start || draft.end !== range.end) && ' · 待应用'}</p>
    </section>
    <section className="card"><div className="card-heading"><div><h2>历史消费趋势</h2><p className="muted history-summary">合计 ¥ {money(days.reduce((sum, day) => sum + day.cents, 0) / 100)}</p></div><div className="segments">{[['month', '月'], ['week', '周'], ['day', '天']].map(([id, label]) => <button key={id} aria-pressed={period === id} className={period === id ? 'selected' : ''} onClick={() => setPeriod(id)}>{label}</button>)}</div></div>
      {points.length ? <Trend points={points} /> : <div className="empty"><Clock3 size={29} /><h3>所选时间范围内暂无消费数据</h3><p>请更换时间范围。演示提供最近 180 天的样例。</p></div>}
    </section>
    <section className="card"><div className="card-heading"><div><h2>监控采集明细</h2><p className="muted">{rangeLabel}<br />余额差 = 本次余额 − 上次余额；负值表示余额减少</p></div><span className="pill">{rows.length ? `${rows.length} 条` : '暂无记录'}</span></div>
      {rows.length ? <><div className="table-scroll"><table><thead><tr>{['获取时间', '余额 / 元', '余额差 / 元', '电表上次度数', '电表当前度数', '度数差 / kWh'].map(title => <th key={title}>{title}</th>)}</tr></thead><tbody>{rows.slice((page - 1) * 10, page * 10).map(row => <tr key={row.time}><td>{row.time}</td><td>¥ {money(row.balance)}</td><td className="consumption">{money(row.delta)}</td><td>{money(row.previousMeter)}</td><td>{money(row.currentMeter)}</td><td>{money(row.units)}</td></tr>)}</tbody></table></div><div className="history-pagination"><span>共 {rows.length} 条 · 第 {page} / {totalPages} 页</span><div><button className="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>上一页</button><button className="secondary" disabled={page === totalPages} onClick={() => setPage(page + 1)}>下一页</button></div></div></> : <div className="empty"><Clock3 size={29} /><h3>{hasHistory ? '所选时间范围内暂无采集记录' : '还没有监控记录'}</h3><p>{hasHistory ? '请更换时间范围，演示提供最近 180 天的样例。' : '开启监控后，这里将展示所选时间范围内的采集明细。'}</p>{!hasHistory && <button className="secondary" onClick={onMonitor}>去设置监控 <ArrowRight size={15} /></button>}</div>}
    </section>
  </>
}

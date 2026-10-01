import { useId, useState } from 'react'
import { addDays, selectableRange, shanghaiDate } from '../../lib/dates.js'

/** @typedef {{start_date: string, end_date: string}} Range */
/** @param {{range: Range, onApply: (range: Range)=>void}} props */
export function DateRangePicker({ range, onApply }) {
  const [draft, setDraft] = useState(range)
  const errorId = useId()
  const valid = selectableRange(draft.start_date, draft.end_date)
  const changed = draft.start_date !== range.start_date || draft.end_date !== range.end_date
  return <form className="range-picker" onSubmit={event => { event.preventDefault(); if (valid) onApply(draft) }}>
    <div className="range-shortcuts">{[7, 30, 90].map(days => <button className="quiet" type="button" key={days}
      onClick={() => setDraft({ start_date: addDays(shanghaiDate(), 1 - days), end_date: shanghaiDate() })}>最近{days}天</button>)}</div>
    <label>开始日期<input type="date" value={draft.start_date} max={shanghaiDate()} aria-invalid={!valid} aria-describedby={!valid ? errorId : undefined} onChange={event => setDraft({ ...draft, start_date: event.target.value })} /></label>
    <label>结束日期<input type="date" value={draft.end_date} max={shanghaiDate()} aria-invalid={!valid} aria-describedby={!valid ? errorId : undefined} onChange={event => setDraft({ ...draft, end_date: event.target.value })} /></label>
    <button disabled={!valid}>应用日期范围</button>
    <p className="muted">当前范围：{range.start_date} 至 {range.end_date}（包含首尾）{changed ? ' · 日期修改尚未应用' : ''}</p>
    {!valid && <p id={errorId} role="alert">请选择不晚于今天、包含首尾且不超过366天的日期范围。</p>}
  </form>
}

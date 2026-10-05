import { useEffect, useId, useRef, useState } from 'react'
import { ArrowRight, CalendarDays } from 'lucide-react'
import { addDays, selectableRange, shanghaiDate } from '../../lib/dates.js'
import { DateCalendar } from './DateCalendar.jsx'

/** @typedef {{start_date: string, end_date: string}} Range */
/** @param {{range: Range, onApply: (range: Range)=>void}} props */
export function DateRangePicker({ range, onApply }) {
  const [draft, setDraft] = useState(range)
  const [active, setActive] = useState(/** @type {'start_date'|'end_date'|null} */ (null))
  const root = useRef(/** @type {HTMLFormElement|null} */ (null))
  const trigger = useRef(/** @type {HTMLButtonElement|null} */ (null))
  const errorId = useId()
  const valid = selectableRange(draft.start_date, draft.end_date)
  const changed = draft.start_date !== range.start_date || draft.end_date !== range.end_date
  useEffect(() => {
    /** @param {PointerEvent} event */
    const outside = event => { if (event.target instanceof Node && !root.current?.contains(event.target)) setActive(null) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [])
  function close() { setActive(null); trigger.current?.focus() }
  return <form ref={root} className="card history-range" onKeyDown={event => {
    if (event.key === 'Escape' && active) { event.preventDefault(); close() }
  }} onSubmit={event => { event.preventDefault(); if (valid) { setActive(null); onApply(draft) } }}>
    <div className="card-heading"><h2><CalendarDays size={18} />时间范围</h2><div className="segments">{[7, 30, 90].map(days => {
      const selected = draft.start_date === addDays(shanghaiDate(), 1 - days) && draft.end_date === shanghaiDate()
      return <button className={selected ? 'selected' : ''} aria-pressed={selected} type="button" key={days}
        onClick={() => { setActive(null); setDraft({ start_date: addDays(shanghaiDate(), 1 - days), end_date: shanghaiDate() }) }}>最近{days}天</button>
    })}</div></div>
    <div className="range-form"><div className="date-picker"><div className="date-fields">
      {/** @type {const} */ (['start_date', 'end_date']).map((field, index) => <div className="date-field-wrap" key={field}>
        {index === 1 && <ArrowRight className="date-field-arrow" size={16} />}
        <div className={`date-field ${active === field ? 'is-open' : ''}`}><button type="button" className="date-trigger" aria-label={`打开${index ? '结束' : '开始'}日期日历`} aria-expanded={active === field}
          onClick={event => { trigger.current = event.currentTarget; setActive(active === field ? null : field) }}><CalendarDays size={19} /></button>
          <label>{index ? '结束日期' : '开始日期'}<input type="date" value={draft[field]} max={shanghaiDate()} aria-invalid={!valid}
            aria-describedby={!valid ? errorId : undefined} onChange={event => setDraft({ ...draft, [field]: event.target.value })} /></label></div>
      </div>)}</div>
      {active && <DateCalendar key={active} field={active} range={draft} onClose={close} onChoose={date => {
        if (active === 'start_date') { setDraft({ start_date: date, end_date: date > draft.end_date ? date : draft.end_date > addDays(date, 365) ? addDays(date, 365) : draft.end_date }); setActive('end_date') }
        else { setDraft({ ...draft, end_date: date }); close() }
      }} />}</div><button className="primary" disabled={!valid}>应用日期范围</button></div>
    <p className="field-hint" aria-live="polite">{range.start_date} 至 {range.end_date}{changed ? ' · 待应用' : ''}</p>
    {!valid && <p id={errorId} className="form-error" role="alert">请选择不晚于今天、包含首尾且不超过366天的日期范围。</p>}
  </form>
}

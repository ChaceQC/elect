import { useEffect, useId, useRef, useState } from 'react'
import { ArrowRight, CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { DEMO_TODAY, shiftDate } from './historyData.js'
import './date-picker.css'

const monthStart = date => `${date.slice(0, 7)}-01`
const moveMonth = (month, offset) => {
  const date = new Date(`${month}T00:00:00Z`)
  date.setUTCMonth(date.getUTCMonth() + offset)
  return date.toISOString().slice(0, 10)
}
export default function DateRangePicker({ value, onChange }) {
  const [active, setActive] = useState(null)
  const [month, setMonth] = useState(monthStart(value.start))
  const [hover, setHover] = useState(null)
  const root = useRef(null)
  const triggers = useRef({})
  const calendarId = useId()
  const offset = (new Date(`${month}T00:00:00Z`).getUTCDay() + 6) % 7
  const first = shiftDate(month, -offset)
  const days = Array.from({ length: 42 }, (_, i) => shiftDate(first, i))
  const previewEnd = active === 'end' && hover && hover >= value.start ? hover : value.end

  useEffect(() => {
    const outside = event => { if (!root.current?.contains(event.target)) setActive(null) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [])
  function close() {
    const field = active
    setActive(null); setHover(null)
    triggers.current[field]?.focus()
  }
  function open(field) {
    if (active === field) return close()
    setMonth(monthStart(value[field])); setHover(null); setActive(field)
  }
  function choose(date) {
    if (active === 'start') {
      onChange({ start: date, end: date > value.end ? date : value.end })
      setActive('end'); setHover(null)
    } else {
      onChange({ start: value.start, end: date })
      close()
    }
  }
  function keyboard(event, date) {
    const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    if (!(event.key in steps)) return
    event.preventDefault()
    const next = shiftDate(date, steps[event.key])
    if (next > DEMO_TODAY || (active === 'end' && next < value.start)) return
    if (!days.includes(next)) setMonth(monthStart(next))
    requestAnimationFrame(() => root.current?.querySelector(`[data-date="${next}"]`)?.focus())
  }
  return <div className="date-picker" ref={root} onKeyDown={event => { if (event.key === 'Escape' && active) { event.preventDefault(); close() } }}>
    <div className="date-fields">{['start', 'end'].map((field, index) => <div className="date-field-wrap" key={field}>
      {index === 1 && <ArrowRight className="date-field-arrow" size={16} />}
      <button type="button" ref={el => { triggers.current[field] = el }} className={`date-field ${active === field ? 'is-open' : ''}`} aria-expanded={active === field} aria-controls={calendarId} onClick={() => open(field)}>
        <CalendarDays size={19} /><span><small>{field === 'start' ? '开始日期' : '结束日期'}</small><strong>{value[field].replaceAll('-', ' / ')}</strong></span>
      </button>
    </div>)}</div>
    {active && <div id={calendarId} className="date-calendar" aria-label={active === 'start' ? '选择开始日期' : '选择结束日期'}>
      <div className="calendar-toolbar">
        <button type="button" aria-label="上个月" className="calendar-arrow" onClick={() => setMonth(moveMonth(month, -1))}><ChevronLeft size={18} /></button>
        <strong aria-live="polite">{Number(month.slice(0, 4))} 年 {Number(month.slice(5, 7))} 月</strong>
        <button type="button" aria-label="下个月" className="calendar-arrow" disabled={moveMonth(month, 1) > DEMO_TODAY} onClick={() => setMonth(moveMonth(month, 1))}><ChevronRight size={18} /></button>
        <button type="button" aria-label="关闭日历" className="calendar-close" onClick={close}><X size={16} /></button>
      </div>
      <div className="calendar-weekdays" aria-hidden="true">{['一', '二', '三', '四', '五', '六', '日'].map(day => <span key={day}>{day}</span>)}</div>
      <div className="calendar-days" onMouseLeave={() => setHover(null)}>{days.map(date => {
        const start = date === value.start
        const end = date === previewEnd
        const between = date > value.start && date < previewEnd
        return <button type="button" key={date} data-date={date} aria-label={date} aria-pressed={start || date === value.end} aria-current={date === DEMO_TODAY ? 'date' : undefined} disabled={date > DEMO_TODAY || (active === 'end' && date < value.start)} className={`calendar-day ${start ? 'range-start' : ''} ${end ? 'range-end' : ''} ${between ? 'in-range' : ''} ${date.slice(0, 7) !== month.slice(0, 7) ? 'other-month' : ''}`} onMouseEnter={() => setHover(date)} onFocus={() => setHover(date)} onKeyDown={event => keyboard(event, date)} onClick={() => choose(date)}><span>{Number(date.slice(8))}</span></button>
      })}</div>
      <div className="calendar-footer"><span>{active === 'start' ? '选择开始日期' : '选择结束日期'}</span><button type="button" onClick={() => setMonth(monthStart(DEMO_TODAY))}>本月</button></div>
    </div>}
  </div>
}

import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { addDays, shanghaiDate } from '../../lib/dates.js'

/** @param {string} date */
const monthStart = date => `${date.slice(0, 7)}-01`
/** @param {string} month @param {number} offset */
function moveMonth(month, offset) {
  const date = new Date(`${month}T00:00:00Z`)
  date.setUTCMonth(date.getUTCMonth() + offset)
  return date.toISOString().slice(0, 10)
}
/** @param {{field: 'start_date'|'end_date', range: import('./DateRangePicker.jsx').Range,
 * onChoose: (date: string)=>void, onClose: ()=>void}} props */
export function DateCalendar({ field, range, onChoose, onClose }) {
  const today = shanghaiDate()
  const initial = range[field] && range[field] <= today ? range[field] : today
  const [month, setMonth] = useState(monthStart(initial))
  const [focused, setFocused] = useState(initial)
  const root = useRef(/** @type {HTMLDivElement|null} */ (null))
  const offset = (new Date(`${month}T00:00:00Z`).getUTCDay() + 6) % 7
  const days = Array.from({ length: 42 }, (_, i) => addDays(month, i - offset))
  const minimum = field === 'end_date' && range.start_date ? range.start_date : null
  const maximum = field === 'end_date' && range.start_date ? [today, addDays(range.start_date, 365)].sort()[0] : today
  useEffect(() => { (/** @type {HTMLButtonElement|null|undefined} */ (root.current?.querySelector(`[data-date="${focused}"]`)))?.focus() }, [focused, month])
  /** @param {string} next */
  function showMonth(next) {
    setMonth(next)
    setFocused(minimum && next < minimum ? minimum : next > maximum ? maximum : next)
  }
  /** @param {import('react').KeyboardEvent} event @param {string} date */
  function keyboard(event, date) {
    const steps = /** @type {Record<string,number>} */ ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 })
    if (!(event.key in steps)) return
    event.preventDefault()
    const next = addDays(date, steps[event.key])
    if (next > maximum || minimum && next < minimum) return
    setFocused(next)
    if (!days.includes(next)) setMonth(monthStart(next))
  }
  return <div className="date-calendar" ref={root} role="group" aria-label={field === 'start_date' ? '选择开始日期' : '选择结束日期'}>
    <div className="calendar-toolbar"><button type="button" aria-label="上个月" className="calendar-arrow" disabled={!!minimum && addDays(month, -1) < minimum} onClick={() => showMonth(moveMonth(month, -1))}><ChevronLeft size={18} /></button>
      <strong aria-live="polite">{Number(month.slice(0, 4))} 年 {Number(month.slice(5, 7))} 月</strong>
      <button type="button" aria-label="下个月" className="calendar-arrow" disabled={moveMonth(month, 1) > maximum} onClick={() => showMonth(moveMonth(month, 1))}><ChevronRight size={18} /></button>
      <button type="button" aria-label="关闭日历" className="calendar-close" onClick={onClose}><X size={16} /></button></div>
    <div className="calendar-weekdays" aria-hidden="true">{['一', '二', '三', '四', '五', '六', '日'].map(day => <span key={day}>{day}</span>)}</div>
    <div className="calendar-days">{days.map(date => <button type="button" key={date} data-date={date} aria-label={date}
      aria-pressed={date === range.start_date || date === range.end_date} aria-current={date === today ? 'date' : undefined}
      disabled={date > maximum || !!minimum && date < minimum} tabIndex={date === focused ? 0 : -1}
      className={`calendar-day ${date === range.start_date ? 'range-start' : ''} ${date === range.end_date ? 'range-end' : ''} ${date > range.start_date && date < range.end_date ? 'in-range' : ''} ${date.slice(0, 7) !== month.slice(0, 7) ? 'other-month' : ''}`}
      onKeyDown={event => keyboard(event, date)} onClick={() => onChoose(date)}><span>{Number(date.slice(8))}</span></button>)}</div>
    <div className="calendar-footer"><span>{field === 'start_date' ? '选择开始日期' : '选择结束日期'}</span><button type="button" disabled={monthStart(today) > maximum} onClick={() => showMonth(monthStart(today))}>本月</button></div>
  </div>
}

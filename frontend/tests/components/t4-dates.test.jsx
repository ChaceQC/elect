import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { DateRangePicker } from '../../src/features/history/DateRangePicker.jsx'
import { addDays, calibrateTime, shanghaiDate } from '../../src/lib/dates.js'

afterEach(() => cleanup())
it('用服务端时间校准上海日期，跨月/闰日含首尾', () => {
  calibrateTime('2026-10-01T23:30:00+08:00')
  expect(shanghaiDate()).toBe('2026-10-01')
  expect(addDays('2024-03-01', -1)).toBe('2024-02-29')
  expect(addDays('2026-10-01', -29)).toBe('2026-09-02')
})
it('修改草稿不应用范围，未来/反向/超过366天阻断提交', () => {
  calibrateTime('2026-10-01T12:00:00+08:00')
  const apply = vi.fn()
  render(<DateRangePicker range={{ start_date: '2026-09-02', end_date: '2026-10-01' }} onApply={apply} />)
  fireEvent.change(screen.getByLabelText('开始日期'), { target: { value: '2026-09-20' } })
  expect(apply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '应用日期范围' }))
  expect(apply).toHaveBeenCalledWith({ start_date: '2026-09-20', end_date: '2026-10-01' })
  fireEvent.change(screen.getByLabelText('结束日期'), { target: { value: '2026-10-02' } })
  expect(screen.getByRole('button', { name: '应用日期范围' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('结束日期'), { target: { value: '2026-09-19' } })
  expect(screen.getByRole('button', { name: '应用日期范围' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('开始日期'), { target: { value: '2025-01-01' } })
  expect(screen.getByRole('button', { name: '应用日期范围' })).toBeDisabled()
})

it('日历箭头跨月保持焦点，选择范围只改草稿，Esc返回触发器', () => {
  calibrateTime('2026-10-01T12:00:00+08:00')
  const apply = vi.fn()
  render(<DateRangePicker range={{ start_date: '2026-09-02', end_date: '2026-10-01' }} onApply={apply} />)
  const trigger = screen.getByRole('button', { name: '打开开始日期日历' })
  fireEvent.click(trigger)
  fireEvent.keyDown(screen.getByRole('button', { name: '2026-08-31' }), { key: 'ArrowLeft' })
  expect(screen.getByRole('button', { name: '2026-08-30' })).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: '2026-08-30' }))
  expect(screen.getByLabelText('开始日期', { exact: true })).toHaveValue('2026-08-30')
  expect(screen.getByRole('button', { name: '2026-10-02' })).toBeDisabled()
  expect(apply).not.toHaveBeenCalled()
  fireEvent.keyDown(screen.getByRole('button', { name: '2026-10-01' }), { key: 'Escape' })
  expect(trigger).toHaveFocus()
  expect(screen.queryByRole('group', { name: '选择结束日期' })).not.toBeInTheDocument()
})

it('通过日历修改开始日期时遵循366天上限，月切换后日期可用键盘继续选择', () => {
  calibrateTime('2026-10-01T12:00:00+08:00')
  render(<DateRangePicker range={{ start_date: '2026-09-02', end_date: '2026-10-01' }} onApply={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '打开开始日期日历' }))
  fireEvent.click(screen.getByRole('button', { name: '上个月' }))
  expect(screen.getByRole('button', { name: '2026-08-01' })).toHaveFocus()
  for (let i = 0; i < 12; i++) fireEvent.click(screen.getByRole('button', { name: '上个月' }))
  fireEvent.click(screen.getByRole('button', { name: '2025-08-01' }))
  expect(screen.getByLabelText('结束日期', { exact: true })).toHaveValue('2026-08-01')
  expect(screen.getByRole('button', { name: '2026-08-02' })).toBeDisabled()
})

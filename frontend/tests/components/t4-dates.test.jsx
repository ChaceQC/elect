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

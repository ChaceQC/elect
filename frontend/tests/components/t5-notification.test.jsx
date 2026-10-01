import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { NotificationStatus } from '../../src/features/monitoring/NotificationStatus.jsx'
import { monitor } from '../fixtures/t3.js'

afterEach(cleanup)

it('SMTP接受和未知结果保留真实边界，未知占次数且不会自动重发', () => {
  const notification = { ...monitor().notification, state: /** @type {const} */ ('delivery_unknown'), delivery_unknown_count: 1 }
  render(<NotificationStatus notification={notification} />)
  expect(screen.getByText(/已占用提醒名额，不会自动重复发送/)).toBeInTheDocument()
  cleanup()
  render(<NotificationStatus notification={{ ...notification, state: 'sent', delivery_unknown_count: 0 }} />)
  expect(screen.getByText(/邮件服务器已接收/)).toBeInTheDocument()
  expect(screen.getByText(/不代表邮箱最终送达或已阅读/)).toBeInTheDocument()
})

it('明确失败和持久重试时间可见', () => {
  render(<NotificationStatus notification={{ ...monitor().notification, state: 'email_failed', last_error_code: 'SMTP_550', next_retry_at: '2026-10-01T12:00:00+08:00' }} />)
  expect(screen.getByText('邮件发送失败')).toBeInTheDocument()
  expect(screen.getByText(/SMTP_550/)).toBeInTheDocument()
  expect(screen.getByText(/邮件下次重试/)).toBeInTheDocument()
})

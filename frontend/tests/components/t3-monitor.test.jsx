import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AppProviders } from '../../src/app/providers.jsx'
import { MonitorPage } from '../../src/features/monitoring/MonitorPage.jsx'
import { apiClient } from '../../src/api/client.js'
import { bindings, envelope, me } from '../fixtures/t2.js'

import { monitor } from '../fixtures/t3.js'

const server = setupServer(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))),
  http.get('/api/v1/room-bindings', () => HttpResponse.json(envelope(bindings))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset() })
afterAll(() => server.close())

it('无效间隔关联可见错误，修正字段后解除无效标记', async () => {
  server.use(http.get('/api/v1/monitor', () => HttpResponse.json(envelope(monitor()))))
  render(<AppProviders><MonitorPage /></AppProviders>)
  const input = await screen.findByLabelText('采集间隔（整数分钟）')
  fireEvent.change(input, { target: { value: '59' } })
  fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  await screen.findByText('采集间隔须为 60–1440 的整数分钟。')
  expect(input).toHaveAttribute('aria-invalid', 'true')
  expect(document.getElementById(input.getAttribute('aria-describedby') ?? '')).toBeVisible()
  fireEvent.change(input, { target: { value: '75' } })
  expect(input).toHaveAttribute('aria-invalid', 'false')
})

it('无效草稿不影响只提交enabled:false的关闭，保留未保存字段', async () => {
  let saved = monitor()
  const writes = /** @type {unknown[]} */ ([])
  server.use(http.get('/api/v1/monitor', () => HttpResponse.json(envelope(saved))),
    http.patch('/api/v1/monitor', async ({ request }) => {
      writes.push(await request.json())
      saved = { ...saved, version: 2, generation: 2, state: 'disabled', config: { ...saved.config, enabled: false } }
      return HttpResponse.json(envelope(saved))
    }))
  render(<AppProviders><MonitorPage /></AppProviders>)
  const interval = await screen.findByLabelText('采集间隔（整数分钟）')
  fireEvent.change(interval, { target: { value: '60.5' } })
  fireEvent.change(screen.getByLabelText('提醒邮箱'), { target: { value: 'invalid' } })
  fireEvent.click(screen.getByLabelText('启用监控'))
  expect(writes).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  await screen.findByText('监控已关闭。其他修改请另行保存。')
  expect(writes).toEqual([{ enabled: false, expected_version: 1 }])
  expect(interval).toHaveValue('60.5')
  expect(screen.getByLabelText('提醒邮箱')).toHaveValue('invalid')
  expect(screen.getByLabelText('启用监控')).not.toBeChecked()
})

it('409展示新的服务端值并保留草稿，明确确认版本后才能保存', async () => {
  let saved = monitor()
  let count = 0
  const writes = /** @type {Record<string,unknown>[]} */ ([])
  server.use(http.get('/api/v1/monitor', () => HttpResponse.json(envelope(saved))),
    http.patch('/api/v1/monitor', async ({ request }) => {
      const body = /** @type {Record<string,unknown>} */ (await request.json())
      writes.push(body); count += 1
      if (count === 1) {
        saved = { ...saved, version: 2, config: { ...saved.config, interval_minutes: 1440 } }
        return HttpResponse.json({ error: { code: 'VERSION_CONFLICT', message: '版本冲突' } }, { status: 409 })
      }
      saved = { ...saved, version: 3, config: { ...saved.config, interval_minutes: 75 } }
      return HttpResponse.json(envelope(saved))
    }))
  render(<AppProviders><MonitorPage /></AppProviders>)
  const interval = await screen.findByLabelText('采集间隔（整数分钟）')
  fireEvent.change(interval, { target: { value: '75' } })
  fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  await screen.findByText('请核对最新保存的设置')
  expect(interval).toHaveValue('75')
  expect(screen.getByText(/采集间隔 1440 分钟/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '保存设置' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '按最新设置继续保存草稿' }))
  fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  await screen.findByText('监控设置已保存。')
  expect(writes.map(body => body.expected_version)).toEqual([1, 2])
  expect(writes[1].interval_minutes).toBe(75)
})

it('背景读取与默认目标变化不能覆盖草稿，重新确认新目标后才解锁', async () => {
  let saved = monitor()
  server.use(http.get('/api/v1/monitor', () => HttpResponse.json(envelope(saved))))
  render(<AppProviders><MonitorPage /></AppProviders>)
  const interval = await screen.findByLabelText('采集间隔（整数分钟）')
  fireEvent.change(interval, { target: { value: '1440' } })
  saved = { ...saved, binding_id: '01970cf0-1234-7000-8000-000000000002', version: 2 }
  fireEvent.click(screen.getByRole('button', { name: '读取最新设置' }))
  await screen.findByText('默认寝室已变化，请确认新目标')
  expect(interval).toHaveValue('1440')
  fireEvent.click(screen.getByRole('button', { name: '采用当前设置，丢弃草稿' }))
  await waitFor(() => expect(interval).toHaveValue('60'))
  expect(screen.getByRole('button', { name: '保存设置' })).toBeEnabled()
})

it.each([
  ['SCHOOL_REAUTH_REQUIRED', '请在“我的账户”中重新学校认证'],
  ['OPERATION_IN_PROGRESS', '寝室或学校认证正在更新'],
])('409 %s 保留对应引导，不要求确认版本', async (code, message) => {
  const saved = { ...monitor(), state: 'disabled', config: { ...monitor().config, enabled: false } }
  server.use(http.get('/api/v1/monitor', () => HttpResponse.json(envelope(saved))),
    http.patch('/api/v1/monitor', () => HttpResponse.json({ error: { code, message: '原始拒绝原因' } }, { status: 409 })))
  render(<AppProviders><MonitorPage /></AppProviders>)
  fireEvent.click(await screen.findByLabelText('启用监控'))
  fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  await screen.findByText(new RegExp(message))
  expect(screen.queryByText('请核对最新保存的设置')).not.toBeInTheDocument()
  expect(screen.getByLabelText('启用监控')).toBeChecked()
})

it('保存期间锁定全部编辑项，响应不会覆盖提交后的新输入；邮件限制直接可见', async () => {
  let release = /** @type {(()=>void)|null} */ (null)
  const pending = new Promise(resolve => { release = () => resolve(null) })
  server.use(http.get('/api/v1/monitor', () => HttpResponse.json(envelope(monitor()))),
    http.patch('/api/v1/monitor', async () => {
      await pending
      return HttpResponse.json(envelope({ ...monitor(), version: 2, config: { ...monitor().config, threshold: '25.00' } }))
    }))
  render(<AppProviders><MonitorPage /></AppProviders>)
  const threshold = await screen.findByLabelText('低余额阈值（元）')
  expect(screen.getByText(/邮件发送未启用：可保存设置并采集余额/)).toBeVisible()
  fireEvent.change(threshold, { target: { value: '25.00' } })
  fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  for (const label of ['低余额阈值（元）', '提醒邮箱', '启用监控', '采集间隔（整数分钟）', '提醒总次数（包含第一次）']) {
    expect(screen.getByLabelText(label)).toBeDisabled()
  }
  fireEvent.change(threshold, { target: { value: '30.00' } })
  expect(threshold).toHaveValue('25.00')
  if (release) /** @type {()=>void} */ (release)()
  await screen.findByText('监控设置已保存。')
  expect(threshold).toBeEnabled()
  expect(threshold).toHaveValue('25.00')
})

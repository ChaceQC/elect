import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AppProviders } from '../../src/app/providers.jsx'
import { CandidateSearch } from '../../src/features/rooms/CandidateSearch.jsx'
import { apiClient } from '../../src/api/client.js'
import { envelope, me } from '../fixtures/t2.js'

const server = setupServer(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset() })
afterAll(() => server.close())

/** @param {string} name @param {string} [expires] */
const result = (name, expires = new Date(Date.now() + 300_000).toISOString()) => ({ items: [
  { candidate_id: name, room_id: name, building: name, number: '001', display_name: `${name}候选`,
    already_bound: false, expires_at: expires }], page: 1, page_size: 10, total: 1,
  search_quality: 'unverified', expires_at: expires })

it('防抖后才请求目标搜索，丢弃迟到的旧候选，遵守至少一秒请求间隔', async () => {
  const calls = /** @type {{q: string|null, time: number}[]} */ ([])
  let release = /** @type {(()=>void)|null} */ (null)
  const held = new Promise(resolve => { release = () => resolve(null) })
  server.use(http.get('/api/v1/room-candidates', async ({ request }) => {
    const q = new URL(request.url).searchParams.get('q')
    calls.push({ q, time: Date.now() })
    if (q === 'Alpha') await held
    return HttpResponse.json(envelope(result(q ?? '')))
  }))
  render(<AppProviders><CandidateSearch /></AppProviders>)
  await waitFor(() => expect(apiClient.csrfToken).toBe(me.csrf_token))
  fireEvent.change(screen.getByLabelText('楼栋或房号'), { target: { value: 'Alpha' } })
  await waitFor(() => expect(calls).toHaveLength(1))
  expect(calls[0].q).toBe('Alpha')
  fireEvent.change(screen.getByLabelText('楼栋或房号'), { target: { value: 'Beta' } })
  await screen.findByText('Beta候选', {}, { timeout: 2500 })
  if (release) /** @type {()=>void} */ (release)()
  expect(screen.queryByText('Alpha候选')).not.toBeInTheDocument()
  expect(calls.map(item => item.q)).toEqual(['Alpha', 'Beta'])
  expect(calls[1].time - calls[0].time).toBeGreaterThanOrEqual(990)
})

it('过期候选显示重新查询，刷新沿用当前页而不显示绑定成功', async () => {
  let count = 0
  server.use(http.get('/api/v1/room-candidates', () => {
    count += 1
    return HttpResponse.json(envelope(result('当前', count === 1 ? '2020-01-01T00:00:00Z' : undefined)))
  }))
  render(<AppProviders><CandidateSearch /></AppProviders>)
  await waitFor(() => expect(apiClient.csrfToken).toBe(me.csrf_token))
  fireEvent.click(screen.getByRole('button', { name: '查询一页' }))
  await screen.findByText('候选已过期，请重新查询')
  expect(screen.queryByText('当前候选')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '查询一页' }))
  await screen.findByText('当前候选', {}, { timeout: 2500 })
  expect(count).toBe(2)
  expect(screen.queryByText('绑定成功')).not.toBeInTheDocument()
})

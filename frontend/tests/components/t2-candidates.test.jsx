import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from '../fixtures/server.js'
import { AppProviders } from '../../src/app/providers.jsx'
import { CandidateSearch } from '../../src/features/rooms/CandidateSearch.jsx'
import { apiClient } from '../../src/api/client.js'
import { envelope, me } from '../fixtures/t2.js'

const server = setupServer(http.get('/api/v1/auth/me', () => HttpResponse.json(envelope(me))))
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); apiClient.reset() })
afterAll(() => server.close())
const choices = () => [
  http.get('/api/v1/room-candidates/buildings', () => HttpResponse.json(envelope({ items: [
    { id: 'b1', label: '枫苑5号' }, { id: 'b2', label: '其他楼栋' }] }))),
  http.get('/api/v1/room-candidates/floors', () => HttpResponse.json(envelope({ items: [{ id: '4', label: '4层' }] }))),
  http.get('/api/v1/room-candidates/rooms', () => HttpResponse.json(envelope({ items: [
    { id: 'r402', label: '402' }, { id: 'r403', label: '403' }] }))),
]
/** @param {string} id @param {string} [expires] */
const result = (id, expires = new Date(Date.now() + 300_000).toISOString()) => ({ items: [
  { candidate_id: id, room_id: id, building: '枫苑5号', number: id.slice(1), display_name: `${id}候选`,
    already_bound: false, expires_at: expires }], page: 1, page_size: 10, total: 1,
  search_quality: 'exact', expires_at: expires })
async function openRooms() {
  await waitFor(() => expect(apiClient.csrfToken).toBe(me.csrf_token))
  fireEvent.click(screen.getByRole('button', { name: '选择寝室' }))
  fireEvent.click(await screen.findByRole('button', { name: '枫苑5号' }))
  fireEvent.click(await screen.findByRole('button', { name: '4层' }))
  await screen.findByRole('button', { name: '402' })
}

it('搜索只过滤三级筛选取得的列表，按room_id核对，丢弃迟到候选', async () => {
  const calls = /** @type {string[]} */ ([])
  let release = /** @type {(()=>void)|null} */ (null)
  const held = new Promise(resolve => { release = () => resolve(null) })
  server.use(...choices(), http.get('/api/v1/room-candidates', async ({ request }) => {
    const params = new URL(request.url).searchParams
    expect(params.has('q')).toBe(false)
    const id = params.get('room_id') ?? ''
    calls.push(id)
    if (id === 'r402') await held
    return HttpResponse.json(envelope(result(id)))
  }))
  render(<AppProviders><CandidateSearch onBind={vi.fn()} /></AppProviders>)
  await openRooms()
  fireEvent.change(screen.getByLabelText('搜索当前房间列表'), { target: { value: '402' } })
  expect(screen.getByRole('button', { name: '402' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '403' })).not.toBeInTheDocument()
  expect(calls).toHaveLength(0)
  fireEvent.change(screen.getByLabelText('搜索当前房间列表'), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: '402' }))
  await waitFor(() => expect(calls).toEqual(['r402']))
  fireEvent.click(screen.getByRole('button', { name: '403' }))
  await screen.findByText('r403候选', {}, { timeout: 2500 })
  if (release) /** @type {()=>void} */ (release)()
  expect(screen.queryByText('r402候选')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '1. 枫苑5号' }))
  expect(screen.queryByText('r403候选')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '2. 选择楼层' })).toBeDisabled()
})

it('过期候选要求重新核对，保留room_id并不显示绑定成功', async () => {
  let count = 0
  server.use(...choices(), http.get('/api/v1/room-candidates', ({ request }) => {
    expect(new URL(request.url).searchParams.get('room_id')).toBe('r402')
    count += 1
    return HttpResponse.json(envelope(result('r402', count === 1 ? '2020-01-01T00:00:00Z' : undefined)))
  }))
  render(<AppProviders><CandidateSearch /></AppProviders>)
  await openRooms()
  fireEvent.click(screen.getByRole('button', { name: '402' }))
  await screen.findByText('候选已过期，请重新核对')
  expect(screen.queryByText('r402候选')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重新核对' }))
  await screen.findByText('r402候选', {}, { timeout: 2500 })
  expect(count).toBe(2)
  expect(screen.queryByText('绑定成功')).not.toBeInTheDocument()
})

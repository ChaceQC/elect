import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from '../auth/SessionProvider.jsx'
import { useNow } from '../../hooks/useNow.js'
import { abortableDelay } from '../../lib/abortableDelay.js'

/** @typedef {import('../../api/generated').components['schemas']['Candidates']} Candidates */
/** @typedef {import('../../api/generated').components['schemas']['Candidate']} Candidate */
/** @typedef {import('../../api/generated').components['schemas']['FilterChoice']} Choice */
/** @typedef {import('../../api/generated').components['schemas']['FilterChoices']} Choices */
/** @param {{onBind?: (candidate: Candidate)=>void, initiallyOpen?: boolean}} props */
export function CandidateSearch({ onBind, initiallyOpen = false } = {}) {
  const { user } = useSession()
  const [opened, setOpened] = useState(initiallyOpen)
  const [building, setBuilding] = useState(/** @type {Choice|null} */ (null))
  const [floor, setFloor] = useState(/** @type {Choice|null} */ (null))
  const [room, setRoom] = useState(/** @type {Choice|null} */ (null))
  const [input, setInput] = useState('')
  const lastRequest = useRef(0)
  const now = useNow()
  const level = !building ? 'buildings' : !floor ? 'floors' : 'rooms'
  const labels = { buildings: '楼栋', floors: '楼层', rooms: '房间' }
  const choices = useQuery({ queryKey: ['room-filters', user?.id, level, building?.id, floor?.id],
    enabled: !!user && opened, retry: false, staleTime: 60_000,
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams()
      if (building) params.set('building_id', building.id)
      if (floor) params.set('floor', floor.id)
      return /** @type {Choices} */ ((await apiClient.request(`/room-candidates/${level}?${params}`, { signal })).data)
    } })
  const candidate = useQuery({ queryKey: ['candidates', user?.id, room?.id], enabled: !!user && !!room,
    retry: false, staleTime: 0,
    queryFn: async ({ signal }) => {
      await abortableDelay(Math.max(0, 1000 - (Date.now() - lastRequest.current)), signal)
      lastRequest.current = Date.now()
      return /** @type {Candidates} */ ((await apiClient.request(`/room-candidates?${new URLSearchParams({
        room_id: /** @type {Choice} */ (room).id, page: '1', page_size: '10' })}`, { signal })).data)
    } })
  const items = choices.data?.items.filter(item => item.label.toLocaleLowerCase().includes(input.trim().toLocaleLowerCase())) ?? []
  /** @param {Choice} item */
  function choose(item) {
    setInput(''); setRoom(null)
    if (level === 'buildings') { setBuilding(item); setFloor(null) }
    else if (level === 'floors') setFloor(item)
    else setRoom(item)
  }
  const selected = candidate.data?.items.find(item => item.room_id === room?.id)
  return <section className="room-section" aria-label="新增学校绑定">
    {!opened ? <button onClick={() => setOpened(true)}>选择寝室</button> : <>
      <div className="filter-steps" aria-label="寝室筛选">
        <button className="quiet" onClick={() => { setBuilding(null); setFloor(null); setRoom(null); setInput('') }}>1. {building?.label ?? '选择楼栋'}</button>
        <button className="quiet" disabled={!building} onClick={() => { setFloor(null); setRoom(null); setInput('') }}>2. {floor?.label ?? '选择楼层'}</button>
        <span>3. {room?.label ?? '选择房间'}</span>
      </div>
      <label className="search-label">搜索当前{labels[level]}列表<input value={input} maxLength={128}
        placeholder={`在已取得的${labels[level]}中查找`} onChange={event => setInput(event.target.value)} /></label>
      <button className="quiet" disabled={choices.isFetching} onClick={() => { setRoom(null); void choices.refetch() }}>刷新当前列表</button>
      {choices.isFetching && <p role="status">正在读取{labels[level]}列表…</p>}
      {choices.error && <StatusBlock title={choices.error.message} error action={{ label: '重试列表', onClick: () => { void choices.refetch() } }} />}
      {choices.data && !choices.isFetching && <>
        {items.length === 0 && <StatusBlock title={choices.data.items.length ? '当前列表没有匹配项' : '学校返回的当前列表为空'} />}
        <ul className="filter-list">{items.map(item => <li key={item.id}><button className="quiet" onClick={() => choose(item)}>{item.label}</button></li>)}</ul>
      </>}
      {room && candidate.isFetching && <p role="status">正在核对所选房间…</p>}
      {room && candidate.error && <StatusBlock title={candidate.error.message} error action={{ label: '重新核对', onClick: () => { void candidate.refetch() } }} />}
      {room && candidate.data && !candidate.isFetching && (Date.parse(candidate.data.expires_at) <= now
        ? <StatusBlock title="候选已过期，请重新核对" action={{ label: '重新核对', onClick: () => { void candidate.refetch() } }} />
        : selected ? <div className="selected-candidate"><strong>{selected.display_name}</strong>
          {selected.already_bound && <p className="muted">该寝室已绑定。</p>}
          <button disabled={selected.already_bound || !onBind} onClick={() => onBind?.(Object.freeze({ ...selected }))}>绑定该寝室</button></div>
          : <StatusBlock title="学校没有确认所选房间，请重新筛选" error />)}
    </>}
  </section>
}

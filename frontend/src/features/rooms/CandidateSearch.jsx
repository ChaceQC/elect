import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from '../auth/SessionProvider.jsx'
import { useNow } from '../../hooks/useNow.js'
import { abortableDelay } from '../../lib/abortableDelay.js'

/** @typedef {import('../../api/generated').components['schemas']['Candidates']} Candidates */
export function CandidateSearch() {
  const { user } = useSession()
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [enabled, setEnabled] = useState(false)
  const lastRequest = useRef(0)
  const now = useNow()
  useEffect(() => {
    const timer = setTimeout(() => { setQ(input.trim()); setPage(1) }, 400)
    return () => clearTimeout(timer)
  }, [input])
  const settled = input.trim() === q
  const query = useQuery({ queryKey: ['candidates', user?.id, { q, page }], enabled: !!user && enabled && settled,
    staleTime: 0, retry: false,
    queryFn: async ({ signal }) => {
      await abortableDelay(Math.max(0, 1000 - (Date.now() - lastRequest.current)), signal)
      lastRequest.current = Date.now()
      return /** @type {Candidates} */ ((await apiClient.request(`/room-candidates?${new URLSearchParams({
        q, page: String(page), page_size: '10' })}`, { signal })).data)
    } })
  return <section className="room-section" aria-labelledby="candidate-title"><h2 id="candidate-title">查找学校寝室</h2>
    <p className="muted">查看学校对当前账号开放的房间；新增绑定功能开放后可选择绑定。</p>
    <label className="search-label">楼栋或房号<input value={input} maxLength={128} placeholder="输入楼栋或房号"
      onChange={event => { setInput(event.target.value); setEnabled(true) }} /></label>
    <button className="quiet" onClick={() => { setEnabled(true); if (enabled) void query.refetch() }} disabled={query.isFetching || !settled}>查询一页</button>
    {query.isFetching && <p role="status">正在查询学校候选…</p>}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重试查询', onClick: () => { void query.refetch() } }} />}
    {query.data && !query.isFetching && settled && <>
      <p className="muted">共 {query.data.total} 条，当前第 {query.data.page} 页。{query.data.search_quality !== 'exact' && '学校筛选精度尚未确认，请核对返回的楼栋与房号。'}</p>
      {Date.parse(query.data.expires_at) <= now ? <StatusBlock title="候选已过期，请重新查询" /> :
        query.data.items.length === 0 ? <StatusBlock title="本页没有候选寝室" /> :
          <ul className="candidate-list">{query.data.items.map(item => <li key={item.candidate_id}><span>{item.display_name}</span>
            <span className="badge">{item.already_bound ? '已绑定' : '可见候选'}</span></li>)}</ul>}
      <div className="pagination"><button className="quiet" disabled={page <= 1 || query.isFetching}
        onClick={() => setPage(page - 1)}>上一页候选</button><button className="quiet" disabled={page * 10 >= query.data.total || query.isFetching}
        onClick={() => setPage(page + 1)}>下一页候选</button></div>
    </>}
  </section>
}

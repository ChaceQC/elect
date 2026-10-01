import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { useOperation } from '../../hooks/useOperation.js'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { useBindings } from './useBindings.js'
import { CandidateSearch } from './CandidateSearch.jsx'

export function RoomsPage() {
  const { user } = useSession()
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [operationId, setOperationId] = useState(/** @type {string|null} */ (null))
  const [error, setError] = useState('')
  const query = useBindings({ q, page })
  const cache = useQueryClient()
  const { controller, submit, busy } = useRequestIntent()
  const pending = query.data?.pending_operations.find(item => item.type === 'binding_sync')
  const terminal = useCallback(() => { void cache.invalidateQueries({ queryKey: ['bindings', user?.id] }) }, [cache, user?.id])
  const operation = useOperation('operation', operationId ?? pending?.id ?? null, terminal)
  async function sync() {
    if (!controller) return
    setError('')
    const retry = controller.restore().find(item => item.path === '/room-bindings/sync' && !item.id)
    try {
      const intent = await submit(retry ?? controller.create('/room-bindings/sync'))
      setOperationId(intent.id)
      await cache.invalidateQueries({ queryKey: ['bindings', user?.id] })
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : '同步受理未确认，请重试原请求。') }
  }
  const data = query.data
  return <><p className="eyebrow">我的寝室生活</p><h1>我的寝室</h1>
    <p className="page-description">从学校同步本人已绑定的寝室与最近余额。</p>
    <div className="room-toolbar"><label className="search-label">搜索本人寝室<input value={q} maxLength={128}
      onChange={event => { setQ(event.target.value); setPage(1) }} placeholder="楼栋或房号" /></label>
      <button onClick={() => { void sync() }} disabled={busy || !!pending}>{busy || pending ? '正在同步…' : '同步学校绑定'}</button></div>
    {error && <StatusBlock title={error} error />}
    {query.isPending && <StatusBlock title="正在读取本人寝室…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取', onClick: () => { void query.refetch() } }} />}
    {operation.data?.state === 'failed' && <StatusBlock title="本次学校同步失败" error><p>错误类别：{'error_code' in operation.data ? String(operation.data.error_code) : '未知'}。已有绑定保留，可以重试同步。</p></StatusBlock>}
    {data && <>
      {['failed', 'stale'].includes(data.sync_status) && <StatusBlock title={data.sync_status === 'stale' ? '学校数据未完成确认' : '尚未成功读取学校绑定'} error>
        <p>请重试同步；当前状态无法确认是否存在绑定。</p></StatusBlock>}
      {data.sync_status === 'loading' && <p role="status">正在同步学校绑定，请稍候…</p>}
      {data.sync_status === 'empty' && data.total === 0 && <StatusBlock title="学校已确认当前没有绑定寝室"><p>可以查询学校候选寝室。</p></StatusBlock>}
      {data.sync_status === 'ready' && data.total === 0 && <StatusBlock title="没有匹配的本人寝室" />}
      <p className="muted">共 {data.total} 条。{data.last_synced_at && `最近同步：${new Date(data.last_synced_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}`}</p>
      <ul className="room-list">{data.items.map(binding => <li key={binding.id} className="room-card">
        <div><h2>{binding.display_name}</h2><p className="muted">{binding.status === 'rechecking' ? '绑定关系待复核' : binding.status === 'inactive' ? '绑定已失效' : '学校已绑定'}
          {data.default_binding_id === binding.id && ' · 默认寝室'}</p></div>
        <div className="room-balance"><span className="muted">最近学校余额{binding.balance?.stale && ' · 已过期'}</span>
          <strong>{binding.balance?.amount == null ? '未知' : moneyLabel(binding.balance.amount)}</strong></div>
      </li>)}</ul>
      {data.items.length > 0 && !data.default_binding_id && <p className="muted">默认寝室设置功能开放后可选择监控目标。</p>}
      <div className="pagination"><button className="quiet" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
        <span>第 {page} 页</span><button className="quiet" disabled={page * 10 >= data.total} onClick={() => setPage(page + 1)}>下一页</button></div>
    </>}
    <CandidateSearch />
  </>
}

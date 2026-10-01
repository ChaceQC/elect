import { useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { useBindings } from './useBindings.js'
import { CandidateSearch } from './CandidateSearch.jsx'
import { BindingDialog } from './BindingDialog.jsx'
import { BindingRecovery } from './BindingRecovery.jsx'
import { RoomOperationStatus } from './RoomOperationStatus.jsx'
import { RemoveBindingDialog } from './RemoveBindingDialog.jsx'
import { PaymentEntry } from '../payments/PaymentEntry.jsx'

export function RoomsPage() {
  const { user } = useSession()
  const location = useLocation()
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [operationId, setOperationId] = useState(/** @type {string|null} */ (null))
  const [error, setError] = useState('')
  const [candidate, setCandidate] = useState(/** @type {import('./CandidateSearch.jsx').Candidate|null} */ (null))
  const [defaultBusy, setDefaultBusy] = useState(false)
  const [removal, setRemoval] = useState(/** @type {import('../../api/generated').components['schemas']['Binding']|null} */ (null))
  const changingDefault = useRef(false)
  const query = useBindings({ q, page })
  const cache = useQueryClient()
  const { controller, submit, busy } = useRequestIntent()
  const pending = query.data?.pending_operations.find(item => item.type === 'binding_sync')
  /** @param {string} id */
  function accepted(id) {
    setOperationId(id)
    void cache.invalidateQueries({ queryKey: ['bindings', user?.id] })
  }
  /** @param {string} id */
  async function setDefault(id) {
    if (changingDefault.current || !query.data) return
    changingDefault.current = true; setDefaultBusy(true); setError('')
    try {
      const result = await apiClient.request('/room-preferences/default', { method: 'PUT',
        body: { binding_id: id, expected_version: query.data.preference_version } })
      if (result.status === 202) accepted(result.data.operation_id)
      else await query.refetch()
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409 ? '默认状态已变化，已保留当前选择，请查看最新状态后再操作。'
        : '切换受理未确认，请先查询最新状态。')
      await query.refetch()
    } finally { changingDefault.current = false; setDefaultBusy(false) }
  }
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
      <button onClick={() => { void sync() }} disabled={busy || !!pending || !!query.data?.binding_removal_operation_id}>{busy || pending ? '正在同步…' : '同步学校绑定'}</button></div>
    {error && <StatusBlock title={error} error />}
    {location.state?.roomUnavailable && <StatusBlock title="所查看的寝室已不可用，已返回本人列表" />}
    {query.isPending && <StatusBlock title="正在读取本人寝室…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取', onClick: () => { void query.refetch() } }} />}
    {[...new Set([operationId, query.data?.default_switch_operation_id, query.data?.binding_removal_operation_id,
      ...(query.data?.pending_operations.map(item => item.id) ?? [])].filter(/** @returns {id is string} */ id => !!id))]
      .map(id => <RoomOperationStatus key={id} id={id} />)}
    <BindingRecovery onAccepted={accepted} />
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
          <strong>{binding.balance?.amount == null ? '未知' : moneyLabel(binding.balance.amount)}</strong>
          <div className="room-actions"><Link to={`/rooms/${binding.id}`}>查看寝室</Link>
            <PaymentEntry bindingId={binding.id} displayName={binding.display_name} />
            <button className="quiet" disabled={binding.status !== 'active' || binding.id === data.default_binding_id ||
              !!data.default_switch_operation_id || !!data.binding_removal_operation_id || defaultBusy} onClick={() => { void setDefault(binding.id) }}>设为默认</button>
            <button className="quiet" disabled={binding.status !== 'active' || !!data.default_switch_operation_id ||
              !!data.binding_removal_operation_id || defaultBusy} onClick={() => setRemoval(binding)}>删除绑定</button></div></div>
      </li>)}</ul>
      {data.items.length > 0 && !data.default_binding_id && <p className="muted">{data.preference_state === 'blocked' ? '默认已清空，请重新选择默认寝室；监控等待新的目标。' : '首次同步会按学校房间标识的稳定顺序初始化默认，完成前以操作进度为准。'}</p>}
      {data.pending_operations_truncated && <p className="muted">待完成操作较多，当前仅展示最近 20 条；默认切换进度单独保留。</p>}
      <div className="pagination"><button className="quiet" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
        <span>第 {page} 页</span><button className="quiet" disabled={page * 10 >= data.total} onClick={() => setPage(page + 1)}>下一页</button></div>
    </>}
    <CandidateSearch onBind={setCandidate} />
    {candidate && <BindingDialog key={candidate.candidate_id} candidate={candidate} onClose={() => setCandidate(null)} onAccepted={accepted} />}
    {removal && <RemoveBindingDialog key={removal.id} binding={removal} isDefault={removal.id === data?.default_binding_id}
      onClose={() => setRemoval(null)} onAccepted={accepted} />}
  </>
}

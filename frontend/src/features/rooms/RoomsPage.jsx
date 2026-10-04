import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'
import { bindingUnavailableReason, useBindings } from './useBindings.js'
import { useNow } from '../../hooks/useNow.js'
import { isBalanceStale } from '../../lib/balance.js'
import { serverNow } from '../../lib/dates.js'
import { CandidateSearch } from './CandidateSearch.jsx'
import { BindingDialog } from './BindingDialog.jsx'
import { BindingRecovery } from './BindingRecovery.jsx'
import { RoomOperationStatus } from './RoomOperationStatus.jsx'
import { RemoveBindingDialog } from './RemoveBindingDialog.jsx'
import { PaymentEntry } from '../payments/PaymentEntry.jsx'
import { Building2, Check, Plus, RefreshCw, Search } from 'lucide-react'
import { PageHeading } from '../../components/layout/PageHeading.jsx'
import { Modal } from '../../components/Modal.jsx'

export function RoomsPage() {
  const { user } = useSession()
  const location = useLocation()
  const [q, setQ] = useState('')
  const [pickerOpen, setPickerOpen] = useState(() => new URLSearchParams(location.search).get('bind') === '1')
  const [page, setPage] = useState(1)
  const [operationId, setOperationId] = useState(/** @type {string|null} */ (null))
  const [error, setError] = useState('')
  const [candidate, setCandidate] = useState(/** @type {import('./CandidateSearch.jsx').Candidate|null} */ (null))
  const [defaultBusy, setDefaultBusy] = useState(false)
  const [defaultTarget, setDefaultTarget] = useState(/** @type {{id: string, name: string, version: number}|null} */ (null))
  const [removal, setRemoval] = useState(/** @type {import('../../api/generated').components['schemas']['Binding']|null} */ (null))
  const changingDefault = useRef(false)
  const query = useBindings({ q, page })
  const now = serverNow(useNow())
  const bindingLimit = bindingUnavailableReason(query.data, user)
  const cache = useQueryClient()
  useEffect(() => {
    if (!query.data) return
    const lastPage = Math.max(1, Math.ceil(query.data.total / 10))
    if (page > lastPage) {
      setPage(lastPage)
      void cache.invalidateQueries({ queryKey: ['bindings', user?.id] })
    }
  }, [query.data, page, cache, user?.id])
  const { controller, submit, busy } = useRequestIntent()
  const pending = query.data?.pending_operations.find(item => item.type === 'binding_sync')
  /** @param {string} id */
  function accepted(id) {
    setOperationId(id)
    void cache.invalidateQueries({ queryKey: ['bindings', user?.id] })
  }
  async function setDefault() {
    if (changingDefault.current || !query.data || !defaultTarget) return
    changingDefault.current = true; setDefaultBusy(true); setError('')
    try {
      const result = await apiClient.request('/room-preferences/default', { method: 'PUT',
        body: { binding_id: defaultTarget.id, expected_version: defaultTarget.version } })
      if (result.status === 202) accepted(result.data.operation_id)
      else await query.refetch()
      setDefaultTarget(null)
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
  return <><PageHeading title="选择与绑定" />
    {error && <StatusBlock title={error} error />}
    {location.state?.roomUnavailable && <StatusBlock title="所查看的寝室已不可用，已返回本人列表" />}
    {query.isPending && <StatusBlock title="正在读取本人寝室…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取', onClick: () => { void query.refetch() } }} />}
    {[...new Set([operationId, query.data?.default_switch_operation_id, query.data?.binding_removal_operation_id,
      ...(query.data?.pending_operations.map(item => item.id) ?? [])].filter(/** @returns {id is string} */ id => !!id))]
      .map(id => <RoomOperationStatus key={id} id={id} />)}
    <BindingRecovery onAccepted={accepted} />
    <section className="card rooms-panel"><div className="card-heading"><h2>已绑定寝室 <span className="count">{data?.total ?? '—'}</span></h2>
      <button className="primary" disabled={!!bindingLimit} onClick={() => setPickerOpen(true)}><Plus size={16} />新增绑定</button></div>
    {bindingLimit && <p role="status">{query.isError ? '暂时无法确认绑定是否开放，请重新读取。' : bindingLimit}</p>}
    {data && data.items.length > 0 && <p className="field-hint">设为默认会同时改变已开启监控的采集与提醒目标。</p>}
    <div className="room-toolbar"><label className="search-box"><Search size={17} aria-hidden="true" /><span className="sr-only">搜索本人寝室</span><input value={q} maxLength={128}
      onChange={event => { setQ(event.target.value); setPage(1) }} placeholder="搜索已绑定的楼栋、寝室号" /></label>
      <button className="quiet" onClick={() => { void sync() }} aria-busy={busy || !!pending} disabled={busy || !!pending || !!query.data?.binding_removal_operation_id}><RefreshCw className={busy || pending ? 'refresh-spinning' : undefined} size={14} aria-hidden="true" />同步学校绑定</button></div>
    {data && <>
      {['failed', 'stale'].includes(data.sync_status) && <StatusBlock title={data.sync_status === 'stale' ? '学校数据未完成确认' : '尚未成功读取学校绑定'} error>
        <p>请重试同步；当前状态无法确认是否存在绑定。</p></StatusBlock>}
      {data.sync_status === 'empty' && data.total === 0 && <StatusBlock title="学校已确认当前没有绑定寝室"><p>可以查询学校候选寝室。</p></StatusBlock>}
      {data.sync_status === 'ready' && data.total === 0 && <StatusBlock title="没有匹配的本人寝室" />}
      <ul className="room-list">{data.items.map(binding => <li key={binding.id} className="room-card room-row">
        <span className="room-icon"><Building2 size={24} /></span><div className="room-name"><h3>{binding.display_name}</h3>
          {binding.status !== 'active' && <p className="muted">{binding.status === 'rechecking' ? '绑定关系待复核' : '绑定已失效'}</p>}</div>
        <div className="room-balance"><span className="muted">最近学校余额{binding.balance && isBalanceStale(binding.balance, now) && ' · 已过期'}</span>
          <strong>{binding.balance?.amount == null ? '—' : moneyLabel(binding.balance.amount)}</strong></div>
          {data.default_binding_id === binding.id ? <span className="pill"><Check size={14} />默认寝室</span> :
            <button className="quiet" disabled={binding.status !== 'active' || !!data.default_switch_operation_id || !!data.binding_removal_operation_id || defaultBusy} onClick={() => setDefaultTarget({ id: binding.id, name: binding.display_name, version: data.preference_version })}>设为默认</button>}
          <div className="room-actions"><Link to={`/rooms/${binding.id}`}>查看寝室</Link>
            <PaymentEntry bindingId={binding.id} displayName={binding.display_name} />
            <button className="quiet" disabled={!!bindingLimit || binding.status !== 'active' || !!data.default_switch_operation_id ||
              !!data.binding_removal_operation_id || defaultBusy} onClick={() => setRemoval(binding)}>删除绑定</button></div>
      </li>)}</ul>
      {data.items.length > 0 && !data.default_binding_id && <p className="muted">{data.preference_state === 'blocked' ? '默认已清空，请重新选择默认寝室；监控等待新的目标。' : '首次同步会按学校返回的顺序初始化默认，完成前以操作进度为准。'}</p>}
      {data.pending_operations_truncated && <p className="muted">待完成操作较多，当前仅展示最近 20 条；默认切换进度单独保留。</p>}
      {(data.total > 10 || page > 1) && <div className="room-list-footer"><p className="muted">共 {data.total} 条</p>
        <div className="pagination"><button className="quiet" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
        <span>第 {page} 页</span><button className="quiet" disabled={page * 10 >= data.total} onClick={() => setPage(page + 1)}>下一页</button></div></div>}
    </>}
    </section>
    <Modal open={pickerOpen} inactive={!!candidate} title="新增绑定寝室" onClose={() => setPickerOpen(false)}>{bindingLimit ? <StatusBlock title={bindingLimit} /> : <CandidateSearch initiallyOpen onBind={setCandidate} />}</Modal>
    {defaultTarget && <Modal open title="确认切换默认寝室" onClose={() => { if (!defaultBusy) setDefaultTarget(null) }}>
      <p>将默认寝室切换到 <strong>{defaultTarget.name}</strong>。已开启的监控会随之切换，之后采集和提醒均以该寝室为目标。</p>
      {error && <StatusBlock title={error} error />}
      <button disabled={defaultBusy} onClick={() => { void setDefault() }}>{defaultBusy ? '正在提交…' : '确认切换'}</button>
    </Modal>}
    {candidate && <BindingDialog key={candidate.candidate_id} candidate={candidate} onClose={() => setCandidate(null)} onAccepted={id => { accepted(id); setPickerOpen(false) }} />}
    {removal && <RemoveBindingDialog key={removal.id} binding={removal} isDefault={removal.id === data?.default_binding_id}
      onClose={() => setRemoval(null)} onAccepted={accepted} />}
  </>
}

import { useEffect, useId, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from '../auth/SessionProvider.jsx'
import { draftFrom, DraftValidationError, parseDraft } from './draft.js'
import { RunControls } from './RunControls.jsx'
import { NotificationStatus } from './NotificationStatus.jsx'
import { Bell, Check, Home, Mail } from 'lucide-react'
import { PageHeading } from '../../components/layout/PageHeading.jsx'
import { useBindings } from '../rooms/useBindings.js'

/** @typedef {import('./draft.js').Monitor} Monitor */
/** @typedef {{draft: import('./draft.js').Draft, baseline: import('./draft.js').Draft,
 * version: number, bindingId: string|null, review: boolean}} Editor */
/** @param {Monitor} saved @returns {Editor} */
const editorFrom = saved => ({ draft: draftFrom(saved), baseline: draftFrom(saved), version: saved.version,
  bindingId: saved.binding_id, review: false })
/** @param {string|null} value */
const when = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '暂无'

export function MonitorPage() {
  const { user } = useSession()
  const cache = useQueryClient()
  const bindings = useBindings({ pageSize: 100 })
  const draftKey = ['monitor-draft', user?.id]
  const query = useQuery({ queryKey: ['monitor', user?.id], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {Monitor} */ ((await apiClient.request('/monitor', { signal })).data),
    refetchInterval: 15_000 })
  const [editor, setEditor] = useState(/** @type {Editor|null} */ (cache.getQueryData(draftKey) ?? null))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [invalidField, setInvalidField] = useState(/** @type {keyof import('./draft.js').Draft|null} */ (null))
  const errorId = useId()
  const [notice, setNotice] = useState('')
  const writing = useRef(false)
  const dirty = !!editor && JSON.stringify(editor.draft) !== JSON.stringify(editor.baseline)
  useEffect(() => {
    if (!query.data) return
    const saved = query.data
    setEditor(old => !old || JSON.stringify(old.draft) === JSON.stringify(old.baseline) && !old.review ? editorFrom(saved) : old)
  }, [query.data])
  useEffect(() => { if (editor) cache.setQueryData(['monitor-draft', user?.id], editor) }, [editor, cache, user?.id])
  useEffect(() => {
    if (!dirty) return
    /** @param {BeforeUnloadEvent} event */
    const guard = event => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [dirty])
  const current = query.data
  const review = !!editor && (!!editor.review || !!current && (editor.version !== current.version || editor.bindingId !== current.binding_id))
  /** @param {Partial<import('./draft.js').Draft>} values */
  function edit(values) {
    setEditor(old => old ? { ...old, draft: { ...old.draft, ...values } } : old)
    if (invalidField && invalidField in values) { setInvalidField(null); setError('') }
  }
  /** @param {boolean} closeOnly */
  async function save(closeOnly) {
    if (writing.current || !current || !editor) return
    let body
    try { body = closeOnly ? { enabled: false, expected_version: current.version } :
      { ...parseDraft(editor.draft), expected_version: editor.version } }
    catch (cause) { setError(cause instanceof Error ? cause.message : '请核对设置。')
      setInvalidField(cause instanceof DraftValidationError ? cause.field : null); return }
    if (!closeOnly && review) { setError('请先核对当前设置和目标，再提交草稿。'); return }
    writing.current = true; setBusy(true); setError(''); setInvalidField(null); setNotice('')
    try {
      const result = await apiClient.request('/monitor', { method: 'PATCH', body })
      const saved = /** @type {Monitor} */ (result.data)
      cache.setQueryData(['monitor', user?.id], saved)
      setEditor(closeOnly ? { ...editorFrom(saved), draft: { ...editor.draft, enabled: false } } : editorFrom(saved))
      setNotice(closeOnly ? '关闭意图已保存。' : '监控设置已保存。')
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409 ? '设置已变化，草稿已保留，请核对当前值。'
        : cause instanceof ApiError && ['NETWORK_ERROR', 'REQUEST_TIMEOUT'].includes(cause.code)
          ? '保存结果尚未确认，请核对已保存设置后决定。' : cause instanceof Error ? cause.message : '保存未完成。')
      setEditor(old => old ? { ...old, review: true } : old)
      await query.refetch()
    } finally { writing.current = false; setBusy(false) }
  }
  const states = { active: '已启用', disabled: '已关闭', requires_reauth: '需要修复学校认证', blocked_room: '需要有效默认寝室', retargeting: '默认寝室切换中' }
  const health = { healthy: '正常', degraded: '部分异常', unavailable: '当前不可用' }
  const room = bindings.data?.items.find(item => item.id === current?.binding_id)
  return <><PageHeading title="监控与预警" />
    {query.isPending && <StatusBlock title="正在读取监控设置…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取', onClick: () => { void query.refetch() } }} />}
    {error && <div id={errorId}><StatusBlock title={error} error /></div>}{notice && <p className="save-notice" role="status">{notice}</p>}
    {current && <section className="monitor-room"><span className="room-icon"><Home size={24} /></span><div><p className="muted">当前监控的默认寝室</p>
      <h3>{room?.display_name ?? (current.binding_id ? bindings.isPending ? '正在读取寝室信息' : '寝室信息暂不可用' : '尚未设置默认寝室')}</h3></div><span className="pill">跟随默认寝室</span></section>}
    {editor && <form className="monitor-form" noValidate onSubmit={event => { event.preventDefault(); void save(false) }}>
      {dirty && <p className="draft-notice">有未保存的修改。</p>}
      {review && current && <StatusBlock title={editor.bindingId !== current.binding_id ? '默认寝室已变化，请确认新目标' : '请核对当前服务端设置'}>
        <p>下方显示当前已保存值，编辑中的草稿已保留。</p>
        <button type="button" className="quiet" onClick={() => setEditor(editorFrom(current))}>采用当前设置，丢弃草稿</button>
        <button type="button" className="quiet" onClick={() => setEditor({ ...editor, baseline: draftFrom(current),
          version: current.version, bindingId: current.binding_id, review: false })}>确认当前目标和版本，保留草稿</button>
      </StatusBlock>}
      <div className="monitor-grid"><section className="card"><div className="card-heading"><h2><Mail size={18} />邮箱与预警</h2></div>
        <label>提醒邮箱<input type="email" placeholder="请输入接收提醒的邮箱" value={editor.draft.email} aria-invalid={invalidField === 'email'} aria-describedby={error ? errorId : undefined} onChange={event => edit({ email: event.target.value })} /></label>
        <label>低余额阈值（元）<input inputMode="decimal" value={editor.draft.threshold} aria-invalid={invalidField === 'threshold'} aria-describedby={error ? errorId : undefined} onChange={event => edit({ threshold: event.target.value })} /></label>
      </section><section className="card"><div className="card-heading"><h2><Bell size={18} />监控设置</h2>
        <label className="switch"><input aria-label="启用监控" type="checkbox" checked={editor.draft.enabled} onChange={event => edit({ enabled: event.target.checked })} /><span /></label></div>
        <label>采集间隔（整数分钟）<input inputMode="numeric" value={editor.draft.interval_minutes} aria-invalid={invalidField === 'interval_minutes'} aria-describedby={error ? errorId : undefined} onChange={event => edit({ interval_minutes: event.target.value })} /></label>
        <label>提醒总次数（包含第一次）<select value={editor.draft.repeat_limit} aria-invalid={invalidField === 'repeat_limit'} aria-describedby={error ? errorId : undefined} onChange={event => edit({ repeat_limit: event.target.value })}>{[1, 2, 3, 4, 5].map(count => <option key={count} value={String(count)}>{count} 次</option>)}</select></label>
      </section></div><div className="save-row"><button disabled={busy || review}><Check size={17} />{busy ? '正在保存…' : '保存设置'}</button>
        <button type="button" className="quiet" disabled={busy} onClick={() => { void save(true) }}>关闭监控</button></div>
    </form>}
    {current && <div className="monitor-alerts">
      {current.state !== 'active' && current.state !== 'disabled' && <p role="alert">{states[current.state]}</p>}
      {current.health !== 'healthy' && current.config.enabled && <p role="status">采集{health[current.health]}{current.last_error_code ? `：${current.last_error_code}` : ''}</p>}
      {current.cancel_pending && <p role="status">正在结束在途工作，已获发送许可的邮件可能完成。</p>}
      {(current.failed_cycles ?? 0) > 3 && <p role="alert">已连续 {current.failed_cycles} 个采集周期失败，请修复最近采集错误；该故障不消耗低余额提醒次数。</p>}
      {(current.notification.state === 'email_failed' || current.notification.delivery_unknown_count > 0) && <NotificationStatus notification={current.notification} />}
    </div>}
    {current && <details className="monitor-details" open={review || undefined}><summary>运行与提醒状态<span>{states[current.state]}</span></summary><div className="monitor-runtime"><section className="card monitor-summary" aria-labelledby="saved-title"><div className="card-heading"><h2 id="saved-title">已保存设置</h2></div>
      <p>控制状态：{states[current.state]} · 采集健康：{health[current.health]}</p>
      <p>采集间隔 {current.config.interval_minutes} 分钟 · 提醒总次数 {current.config.repeat_limit}（包含第一次）· 阈值 {current.config.threshold} 元</p>
      <p>提醒邮箱：{current.config.email ?? '未设置'}</p><p>最近成功采集：{when(current.last_success_at)} · 下一计划时间：{when(current.next_run_at)}</p>
      <NotificationStatus notification={current.notification} />
      <p>在途工作 {current.in_flight_count} 项</p>
      {current.last_error_code && <p>最近采集错误：{current.last_error_code}</p>}
      {current.cancel_pending && <p>取消正在确认；已获发送许可的在途邮件可能完成。</p>}
      <div className="actions"><button className="quiet" disabled={busy || query.isFetching} onClick={() => { void query.refetch() }}>读取最新设置</button></div>
      {!current.notification.delivery_enabled && <p className="muted">邮件发送未启用。</p>}
      <p className="muted">退出应用不关闭监控；关闭监控保留历史。</p>
    </section><RunControls monitor={current} /></div></details>}
  </>
}

import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from '../auth/SessionProvider.jsx'
import { draftFrom, parseDraft } from './draft.js'
import { RunControls } from './RunControls.jsx'
import { NotificationStatus } from './NotificationStatus.jsx'

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
  const draftKey = ['monitor-draft', user?.id]
  const query = useQuery({ queryKey: ['monitor', user?.id], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {Monitor} */ ((await apiClient.request('/monitor', { signal })).data),
    refetchInterval: 15_000 })
  const [editor, setEditor] = useState(/** @type {Editor|null} */ (cache.getQueryData(draftKey) ?? null))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
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
  function edit(values) { setEditor(old => old ? { ...old, draft: { ...old.draft, ...values } } : old) }
  /** @param {boolean} closeOnly */
  async function save(closeOnly) {
    if (writing.current || !current || !editor) return
    let body
    try { body = closeOnly ? { enabled: false, expected_version: current.version } :
      { ...parseDraft(editor.draft), expected_version: editor.version } }
    catch (cause) { setError(cause instanceof Error ? cause.message : '请核对设置。'); return }
    if (!closeOnly && review) { setError('请先核对当前设置和目标，再提交草稿。'); return }
    writing.current = true; setBusy(true); setError(''); setNotice('')
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
  return <><p className="eyebrow">我的寝室生活</p><h1>监控提醒</h1>
    <p className="page-description">设置跟随默认寝室，关闭监控会保留历史。退出网页与撤回学校授权具有不同作用。</p>
    <StatusBlock title="后台采集与邮件提醒"><p>监控按已保存设置在后台采集余额，余额严格低于阈值时提醒；总次数包含第一封。关闭后保留历史，退出应用不会关闭监控。</p>
      {current && !current.notification.delivery_enabled && <p>当前邮件发送未启用，可保存设置；启用后的投递结果会显示在下方。</p>}
    </StatusBlock>
    {query.isPending && <StatusBlock title="正在读取监控设置…" />}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取', onClick: () => { void query.refetch() } }} />}
    {error && <StatusBlock title={error} error />}{notice && <p role="status">{notice}</p>}
    {current && <section className="monitor-summary" aria-labelledby="saved-title"><h2 id="saved-title">已保存设置</h2>
      <p>控制状态：{states[current.state]} · 采集健康：{health[current.health]}</p>
      <p>采集间隔 {current.config.interval_minutes} 分钟 · 提醒总次数 {current.config.repeat_limit}（包含第一次）· 阈值 {current.config.threshold} 元</p>
      <p>提醒邮箱：{current.config.email ?? '未设置'} · 最近成功采集：{when(current.last_success_at)} · 下一计划时间：{when(current.next_run_at)}</p>
      <NotificationStatus notification={current.notification} />
      <p>在途工作 {current.in_flight_count} 项</p>
      {current.last_error_code && <p>最近采集错误：{current.last_error_code}</p>}
      {(current.failed_cycles ?? 0) > 3 && <p role="alert">已连续 {current.failed_cycles} 个采集周期失败，请修复最近采集错误；该故障不消耗低余额提醒次数。</p>}
      {current.cancel_pending && <p>取消正在确认；已获发送许可的在途邮件可能完成。</p>}
      <button className="quiet" disabled={busy} onClick={() => { void save(true) }}>关闭监控</button>
      <button className="quiet" disabled={busy || query.isFetching} onClick={() => { void query.refetch() }}>读取最新设置</button>
    </section>}
    {current && <RunControls monitor={current} />}
    {editor && <form className="monitor-form" noValidate onSubmit={event => { event.preventDefault(); void save(false) }}><h2>编辑设置</h2>
      {dirty && <p className="muted">有未保存的草稿。离开页面后，本次会话会保留草稿；刷新前请保存。</p>}
      {review && current && <StatusBlock title={editor.bindingId !== current.binding_id ? '默认寝室已变化，请确认新目标' : '请核对当前服务端设置'}>
        <p>上方显示当前已保存值，草稿保留在下方。</p>
        <button type="button" className="quiet" onClick={() => setEditor(editorFrom(current))}>采用当前设置，丢弃草稿</button>
        <button type="button" className="quiet" onClick={() => setEditor({ ...editor, baseline: draftFrom(current),
          version: current.version, bindingId: current.binding_id, review: false })}>确认当前目标和版本，保留草稿</button>
      </StatusBlock>}
      <label className="checkbox-label"><input type="checkbox" checked={editor.draft.enabled} onChange={event => edit({ enabled: event.target.checked })} />启用监控</label>
      <label>采集间隔（整数分钟）<input inputMode="numeric" value={editor.draft.interval_minutes} onChange={event => edit({ interval_minutes: event.target.value })} /></label>
      <label>提醒总次数（包含第一次）<input inputMode="numeric" value={editor.draft.repeat_limit} onChange={event => edit({ repeat_limit: event.target.value })} /></label>
      <label>低余额阈值（元）<input inputMode="decimal" value={editor.draft.threshold} onChange={event => edit({ threshold: event.target.value })} /></label>
      <label>提醒邮箱<input type="email" value={editor.draft.email} onChange={event => edit({ email: event.target.value })} /></label>
      <button disabled={busy || review}>{busy ? '正在保存…' : '保存设置'}</button>
    </form>}
  </>
}

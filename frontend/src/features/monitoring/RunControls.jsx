import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useOperation } from '../../hooks/useOperation.js'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { timestampLabel } from '../../lib/dates.js'
import { useSession } from '../auth/SessionProvider.jsx'

/** @typedef {import('../../api/generated').components['schemas']['Run']} Run */
/** @param {{monitor: import('./draft.js').Monitor}} props */
export function RunControls({ monitor }) {
  const { user } = useSession()
  const cache = useQueryClient()
  const { controller, submit, busy } = useRequestIntent()
  const [intent, setIntent] = useState(/** @type {import('../../api/intents.js').Intent|null} */ (null))
  const [error, setError] = useState('')
  const [cancelling, setCancelling] = useState(false)
  useEffect(() => {
    const saved = controller?.restore().find(item => item.kind === 'run')
    const current = monitor.current_run?.id ?? monitor.last_run?.id
    const recovered = current ? controller?.recoverSummaries('run', [current]).find(item => item.id === current) : saved
    setIntent(recovered ?? null)
  }, [controller, monitor.current_run?.id, monitor.last_run?.id])
  const operation = useOperation('run', intent?.id ?? null, () => {
    if (intent) controller?.forget(intent.key)
    for (const key of ['monitor', 'balance', 'samples', 'overview', 'bindings']) void cache.invalidateQueries({ queryKey: [key, user?.id] })
  })
  const run = /** @type {Run|undefined} */ (operation.data) ?? monitor.current_run ?? monitor.last_run
  const active = run && ['pending', 'running', 'retry_wait', 'cancel_requested'].includes(run.state)
  const names = { pending: '等待采集', running: '正在采集', retry_wait: '等待重试', cancel_requested: '正在结束本次请求', succeeded: '采集已完成', failed: '采集失败', cancelled: '本次已取消' }
  async function start() {
    if (!controller || busy) return
    const next = intent && !intent.id ? intent : controller.create('/monitor/runs', {}, 'run')
    setIntent(next); setError('')
    try { setIntent(await submit(next)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '受理结果尚未确认，请恢复原请求。') }
  }
  async function cancel() {
    if (!run || cancelling) return
    setCancelling(true); setError('')
    try { await apiClient.request(`/monitor/runs/${run.id}/cancel`, { method: 'POST', body: { expected_version: run.version } }) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '取消结果尚未确认，请读取最新运行。') }
    finally { await operation.refresh(); void cache.invalidateQueries({ queryKey: ['monitor', user?.id] }); setCancelling(false) }
  }
  return <section className="data-card"><h2>本次采集</h2>
    <button disabled={busy || !!active || !!intent?.id && operation.isPending || !monitor.config.enabled || monitor.state !== 'active'} onClick={() => { void start() }}>{busy ? '正在受理…' : intent && !intent.id ? '查询原采集请求' : '立即采集'}</button>
    <p className="muted">取消本次采集不关闭后续计划；已完成的采集记录保留。</p>
    {run && <><p role="status">{names[run.state]}</p><p>计划时间：{timestampLabel(run.scheduled_for)} · 尝试{run.attempts.length}次</p>
      {run.binding_id !== monitor.binding_id && <p>该运行属于切换前的寝室，当前设置已使用新目标。</p>}
      {run.next_attempt_at && <p>下次重试：{timestampLabel(run.next_attempt_at)}</p>}
      {run.error_code && <p role="alert">采集错误：{run.error_code}</p>}
      <button className="quiet" disabled={cancelling || !['pending', 'running', 'retry_wait'].includes(run.state)} onClick={() => { void cancel() }}>取消本次采集</button></>}
    {intent?.id && <button className="quiet" disabled={operation.isFetching} onClick={() => { void operation.refresh() }}>读取最新运行</button>}
    {(error || operation.error) && <StatusBlock title={error || operation.error?.message || '运行查询失败'} error />}
  </section>
}

import { useContext, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useOperation } from '../../hooks/useOperation.js'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { PollingNotice } from '../../components/feedback/PollingNotice.jsx'
import { useSession } from '../auth/SessionProvider.jsx'
import { RefreshCw } from 'lucide-react'
import { QueryRefreshContext } from './QueryRefreshProvider.jsx'

/** @param {{path: string, body?: import('../../api/intents.js').SafeBody, label: string, operationId?: string, compact?: boolean, autoRefresh?: boolean}} props */
export function QueryAction({ path, body = {}, label, operationId, compact = false, autoRefresh = false }) {
  const { user, profile } = useSession()
  const cache = useQueryClient()
  const { controller, submit, busy, coolingDown } = useRequestIntent()
  const [intent, setIntent] = useState(/** @type {import('../../api/intents.js').Intent|null} */ (null))
  const [error, setError] = useState('')
  const attempted = useContext(QueryRefreshContext)
  useEffect(() => {
    const recovered = controller?.restore().find(item => item.path === path)
      ?? (operationId ? controller?.recoverSummaries('operation', [operationId]).find(item => item.id === operationId) : null)
    setIntent(recovered ?? null); setError('')
  }, [controller, path, operationId])
  useEffect(() => {
    if (!autoRefresh || !attempted || attempted.has(path) || !controller || busy ||
      profile?.credential_status !== 'active' || !profile.consent.credential_use_allowed) return
    attempted.add(path)
    const recovered = controller.restore().find(item => item.path === path)
      ?? (operationId ? controller.recoverSummaries('operation', [operationId]).find(item => item.id === operationId) : null)
    const next = recovered ?? controller.create(path, body)
    setIntent(next); setError('')
    // 已受理的请求只恢复轮询；受理未知或限流请求沿用原键及原日期范围。
    if (next.id) return
    void submit(next).then(setIntent).catch(cause => {
      setError(cause instanceof Error ? cause.message : '查询受理未确认，请查询原操作。')
    })
  }, [autoRefresh, attempted, controller, busy, profile, path, body, operationId, submit])
  const operation = useOperation('operation', intent?.id ?? null, value => {
    if (intent) controller?.forget(intent.key)
    for (const key of ['balance', 'consumption', 'overview', 'bindings', 'samples']) void cache.invalidateQueries({ queryKey: [key, user?.id] })
    if (value.state === 'failed') setError('本次查询未完成，已保留最近成功数据。')
  })
  const running = intent && (!intent.id || !['succeeded', 'failed', 'cancelled'].includes(operation.data?.state ?? ''))
  const refreshing = busy || !!intent?.id && !!running && !operation.pollingPaused
  async function start() {
    if (!profile || !controller || busy || coolingDown) return
    const next = running && intent ? intent : controller.create(path, body)
    setIntent(next); setError('')
    try { setIntent(await submit(next)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '查询受理未确认，请查询原操作。') }
  }
  return <div className="query-action">
    <button className="quiet" title={!profile ? '学校资料暂不可用' : compact ? label : undefined} aria-busy={refreshing} disabled={!profile || busy || coolingDown || !!intent?.id && !!running} onClick={() => { void start() }}><RefreshCw className={refreshing ? 'refresh-spinning' : undefined} size={14} aria-hidden="true" /><span className={compact ? 'sr-only' : undefined}>{!busy && running && !intent?.id ? '查询原请求的受理结果' : label}</span></button>
    {refreshing && <span className="sr-only" role="status">正在刷新</span>}
    {operation.data?.state === 'unknown' && <p role="status">查询结果尚未确认</p>}
    {operation.data?.state === 'cancelled' && <p role="status">查询已取消</p>}
    {(error || operation.error) && <StatusBlock title={error || operation.error?.message || '查询未完成'} error />}
    <PollingNotice paused={operation.pollingPaused} busy={operation.isFetching} onResume={() => { void operation.refresh() }} />
  </div>
}

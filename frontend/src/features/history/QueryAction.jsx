import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useOperation } from '../../hooks/useOperation.js'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from '../auth/SessionProvider.jsx'
import { RefreshCw } from 'lucide-react'

/** @param {{path: string, body?: import('../../api/intents.js').SafeBody, label: string, operationId?: string, compact?: boolean}} props */
export function QueryAction({ path, body = {}, label, operationId, compact = false }) {
  const { user } = useSession()
  const cache = useQueryClient()
  const { controller, submit, busy } = useRequestIntent()
  const [intent, setIntent] = useState(/** @type {import('../../api/intents.js').Intent|null} */ (null))
  const [error, setError] = useState('')
  useEffect(() => {
    const recovered = controller?.restore().find(item => item.path === path)
      ?? (operationId ? controller?.recoverSummaries('operation', [operationId]).find(item => item.id === operationId) : null)
    setIntent(recovered ?? null); setError('')
  }, [controller, path, operationId])
  const operation = useOperation('operation', intent?.id ?? null, value => {
    if (intent) controller?.forget(intent.key)
    for (const key of ['balance', 'consumption', 'overview', 'bindings', 'samples']) void cache.invalidateQueries({ queryKey: [key, user?.id] })
    if (value.state === 'failed') setError('本次查询未完成，已保留最近成功数据。')
  })
  const running = intent && (!intent.id || !['succeeded', 'failed', 'cancelled'].includes(operation.data?.state ?? ''))
  async function start() {
    if (!controller || busy) return
    const next = running && intent ? intent : controller.create(path, body)
    setIntent(next); setError('')
    try { setIntent(await submit(next)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '查询受理未确认，请查询原操作。') }
  }
  return <div className="query-action">
    <button className="quiet" title={compact ? label : undefined} disabled={busy || !!intent?.id && !!running} onClick={() => { void start() }}><RefreshCw size={14} aria-hidden="true" /><span className={compact && !busy && !running ? 'sr-only' : undefined}>{busy ? '正在受理…' : running ? intent?.id ? '查询已受理，等待结果' : '查询原请求的受理结果' : label}</span></button>
    {operation.data && <p role="status">{({ accepted: '查询已受理', running: '正在从学校读取', succeeded: '查询已完成', failed: '查询失败，保留已有数据', cancelled: '查询已取消', reconciling: '结果确认中', unknown: '查询结果尚未确认' })[operation.data.state] ?? operation.data.state}</p>}
    {running && intent?.body.start_date && <p className="muted">本次同步范围：{intent.body.start_date} 至 {intent.body.end_date}</p>}
    {(error || operation.error) && <StatusBlock title={error || operation.error?.message || '查询未完成'} error />}
    {running && intent?.id && <button className="quiet" onClick={() => { void operation.refresh() }}>查询最新进度</button>}
  </div>
}

import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useOperation } from '../../hooks/useOperation.js'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { PollingNotice } from '../../components/feedback/PollingNotice.jsx'
import { useSession } from '../auth/SessionProvider.jsx'

/** @param {{id: string}} props */
export function RoomOperationStatus({ id }) {
  const { user } = useSession()
  const cache = useQueryClient()
  const { controller } = useRequestIntent()
  const terminal = useCallback(() => {
    for (const name of ['bindings', 'monitor', 'binding-view', 'overview']) void cache.invalidateQueries({ queryKey: [name, user?.id] })
    for (const intent of controller?.restore() ?? []) if (intent.id === id) controller?.forget(intent.key)
  }, [cache, user?.id, controller, id])
  const query = useOperation('operation', id, terminal)
  const data = /** @type {import('../../api/generated').components['schemas']['Operation']|undefined} */ (query.data)
  const types = /** @type {Record<string,string>} */ ({ bind_room: '学校绑定', unbind_room: '学校解绑', switch_default: '默认切换', binding_sync: '学校同步' })
  const states = { accepted: '已受理', running: '处理中', reconciling: '正在确认', unknown: '结果尚未确认', succeeded: '已完成', failed: '未完成', cancelled: '已取消' }
  const bindings = { pending: '待学校确认', confirmed: '学校已确认', removed: '学校已解除绑定', failed: '学校绑定失败', unknown: '学校结果未知' }
  const defaults = { pending: '等待绑定结果', switching: '默认切换中', confirmed: '默认已确认', unchanged: '保留原默认', failed: '默认设置失败，已绑定关系保留' }
  return <StatusBlock title={data ? `${types[data.type] ?? '操作'}：${states[data.state]}` : '正在读取操作进度…'} error={!!query.error || data?.state === 'failed'}>
    {data?.binding_status && <p>{data.type === 'unbind_room' ? '解绑' : '绑定'}状态：{bindings[data.binding_status]}</p>}
    {data?.default_status && <p>默认状态：{data.type === 'unbind_room' && data.default_status === 'confirmed' ? '已清空默认，监控等待新目标' : defaults[data.default_status]}</p>}
    {data?.state === 'unknown' && <p>后台只回查学校结果，请勿重复提交。等待时间不会被当作操作失败。</p>}
    {data?.error_code && <p className="muted">最近错误：{data.error_code}</p>}
    {query.error && <p>{query.error.message}</p>}
    <PollingNotice paused={query.pollingPaused} busy={query.isFetching} onResume={() => { void query.refresh() }} />
  </StatusBlock>
}

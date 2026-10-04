import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { PollingNotice } from '../../components/feedback/PollingNotice.jsx'
import { useOperation } from '../../hooks/useOperation.js'
import { useSession } from './SessionProvider.jsx'

// 保留升级前已受理操作的进度，页面不再创建新的撤回请求。
export function CredentialProgress() {
  const { user, refreshUser } = useSession()
  const cache = useQueryClient()
  const [error, setError] = useState('')
  const terminal = useCallback(async () => {
    try { await refreshUser(); await cache.invalidateQueries({ queryKey: ['monitor', user?.id] }) }
    catch { setError('账户信息暂未刷新，请重新查询。') }
  }, [refreshUser, cache, user?.id])
  const operation = useOperation('operation', user?.credential_revoke_operation?.id ?? null, terminal)
  if (user?.credential_status !== 'revoking' && !error) return null
  return <StatusBlock title="学校认证正在更新…">
    <p>正在停止旧后台任务并处理已提交的凭据变更，完成后可重新认证。</p>
    {(error || operation.error) && <p role="alert">{error || operation.error?.message}</p>}
    <PollingNotice paused={operation.pollingPaused} busy={operation.isFetching} onResume={() => { void operation.refresh() }} />
    <button className="quiet" onClick={() => {
      void refreshUser().catch(() => setError('账户信息暂时不可用，请稍后查询。'))
      if (user?.credential_revoke_operation) void operation.refresh()
    }}>查询认证进度</button>
  </StatusBlock>
}

import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useOperation } from '../../hooks/useOperation.js'
import { useSession } from './SessionProvider.jsx'

export function RevokeCredential() {
  const { user, refreshUser } = useSession()
  const cache = useQueryClient()
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [id, setId] = useState(/** @type {string|null} */ (null))
  const submitting = useRef(false)
  const terminal = useCallback(async () => {
    try {
      await refreshUser()
      await cache.invalidateQueries({ queryKey: ['monitor', user?.id] })
    } catch { setError('操作已结束，账户信息暂未刷新，请重新查询。') }
  }, [refreshUser, cache, user?.id])
  const operation = useOperation('operation', id ?? user?.credential_revoke_operation?.id ?? null, terminal)
  const pending = user?.credential_status === 'revoking' || Boolean(
    (id || user?.credential_revoke_operation) && !['succeeded', 'failed', 'cancelled'].includes(operation.data?.state ?? ''),
  )
  async function revoke() {
    if (submitting.current || !confirmed || !user?.credential_version) return
    submitting.current = true; setBusy(true); setError('')
    try {
      const result = await apiClient.request('/auth/school-credential', {
        method: 'DELETE', body: { expected_version: user.credential_version },
      })
      setId(result.data.operation_id)
      setConfirmed(false)
      await refreshUser()
    } catch (failure) {
      setConfirmed(false)
      setError(failure instanceof ApiError && failure.status === 409
        ? '凭据状态已变化，请刷新账户后再操作。'
        : '撤回结果尚未确认，请查询账户和操作进度。')
      try { await refreshUser() } catch { /* 保留可见错误和查询入口。 */ }
    } finally { submitting.current = false; setBusy(false) }
  }
  if (user?.credential_status === 'revoked') return <StatusBlock title="后台授权已撤回">
    <p>已保存的学校凭据已删除，后台监控已关闭。应用会话和历史记录保留。</p>
  </StatusBlock>
  return <section aria-label="撤回后台授权">
    {pending ? <StatusBlock title="正在撤回后台授权…"><p>正在确认监控屏障和凭据删除，完成状态以服务器为准。</p></StatusBlock> : <>
      <p>撤回会关闭后台监控并删除保存的学校凭据。已获发送许可的在途邮件可能完成投递。</p>
      <label><input type="checkbox" checked={confirmed} disabled={busy}
        onChange={event => setConfirmed(event.target.checked)} />确认撤回后台授权并删除学校凭据</label>
      <button className="quiet" disabled={!confirmed || busy || !user?.credential_version}
        onClick={() => { void revoke() }}>{busy ? '正在受理…' : '撤回后台授权'}</button>
    </>}
    {error && <StatusBlock title={error} error />}
    {operation.isError && <StatusBlock title="暂时无法读取撤回进度，操作会在后台继续。" error />}
    {(pending || error || operation.isError) && <button className="quiet" onClick={() => {
      void refreshUser().catch(() => setError('账户信息暂时不可用，请稍后查询。'))
      void operation.refresh()
    }}>查询撤回进度</button>}
  </section>
}

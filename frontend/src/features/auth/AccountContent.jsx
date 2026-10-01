import { useState } from 'react'
import { apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from './SessionProvider.jsx'
import { LoginForm } from './LoginForm.jsx'

/** @param {{onClose: ()=>void}} props */
export function AccountContent({ onClose }) {
  const { user, endSession } = useSession()
  const [repairing, setRepairing] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function logout() {
    if (busy) return
    setBusy(true); setError('')
    try { await apiClient.request('/auth/logout', { method: 'POST' }); await endSession() }
    catch { setError('退出未完成，请稍后重试。') }
    finally { setBusy(false) }
  }
  return <><p>{user?.school}</p><p>学校账号：{user?.student_id}</p>
    <p>学校认证：{user?.credential_status === 'active' ? '可用' : '需要修复或已撤回'}</p>
    <p>后台凭据使用：{user?.consent.credential_use_allowed ? '已授权' : '未授权'}</p>
    <p className="muted">退出应用不会关闭已授权的后台监控。</p>
    {error && <StatusBlock title={error} error />}
    {repairing ? <LoginForm reauthenticate onSuccess={onClose} /> :
      <button className="quiet" onClick={() => setRepairing(true)}>重新学校认证</button>}
    <p className="muted">撤回后台授权功能尚未开放。</p>
    <button onClick={() => { void logout() }} disabled={busy}>{busy ? '正在退出…' : '退出应用'}</button>
  </>
}

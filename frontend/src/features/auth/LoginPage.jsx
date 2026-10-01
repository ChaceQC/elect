import { Navigate, useLocation } from 'react-router-dom'
import { useSession } from './SessionProvider.jsx'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { LoginForm } from './LoginForm.jsx'

export function LoginPage() {
  const session = useSession()
  const location = useLocation()
  if (session.status === 'authenticated') {
    const from = location.state?.from
    const destination = ['/overview', '/details', '/rooms', '/monitor'].some(path =>
      from === path || from?.startsWith(`${path}?`)) ? from : '/overview'
    return <Navigate to={destination} replace />
  }
  return <main id="main-content" className="foundation login-page">
    <span className="brand">ELECT · 寝室电力</span><h1>寝室用电，心中有数。</h1>
    <p>使用学校账号管理寝室、查询电费并设置余额提醒。</p>
    {session.status === 'initializing' ? <StatusBlock title="正在恢复会话…" /> : session.status === 'signed_out' ? <LoginForm /> :
      <StatusBlock error={session.status === 'unavailable'}
        title={session.error?.code === 'FEATURE_DISABLED' ? '登录服务尚未开放' :
          session.status === 'unavailable' ? '暂时无法连接登录服务' : '学校账号登录即将开放'}
        action={{ label: '重新检查', onClick: () => { void session.initialize() } }}>
        <p>服务开放后可使用学校验证码登录。</p>
      </StatusBlock>}
  </main>
}

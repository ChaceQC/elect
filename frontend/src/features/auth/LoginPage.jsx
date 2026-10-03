import { Navigate, useLocation } from 'react-router-dom'
import { useSession } from './SessionProvider.jsx'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { LoginForm } from './LoginForm.jsx'
import { Home, Zap } from 'lucide-react'
import { Brand } from '../../components/layout/Brand.jsx'

export function LoginPage() {
  const session = useSession()
  const location = useLocation()
  if (session.status === 'authenticated') {
    const from = location.state?.from
    const destination = ['/overview', '/details', '/rooms', '/monitor'].some(path =>
      from === path || from?.startsWith(`${path}?`)) ? from : '/overview'
    return <Navigate to={destination} replace />
  }
  return <main id="main-content" className="login-layout">
    <section className="login-story"><Brand /><div className="story-copy">
      <h1>每一度电，<br />心中有数<span>。</span></h1>
      <div className="energy-art" aria-hidden="true"><div className="orbit one" /><div className="orbit two" />
        <div className="art-home"><Home size={82} strokeWidth={1} /><span className="art-bolt"><Zap fill="currentColor" size={25} /></span></div>
        <span className="art-value">ELECT</span></div>
    </div></section>
    <section className="login-panel"><div className="login-card"><span className="pill">学生服务中心</span><h2>欢迎回来</h2>
    {session.status === 'initializing' ? <StatusBlock title="正在恢复会话…" /> : session.status === 'signed_out' ? <LoginForm /> :
      <StatusBlock error={session.status === 'unavailable'}
        title={session.error?.code === 'FEATURE_DISABLED' ? '登录服务尚未开放' :
          session.status === 'unavailable' ? '暂时无法连接登录服务' : '学校账号登录即将开放'}
        action={{ label: '重新检查', onClick: () => { void session.initialize() } }}>
        <p>服务开放后可使用学校验证码登录。</p>
      </StatusBlock>}
    </div></section></main>
}

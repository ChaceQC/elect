import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../features/auth/SessionProvider.jsx'
import { StatusBlock } from '../components/feedback/StatusBlock.jsx'

export function AuthGuard() {
  const session = useSession()
  const location = useLocation()
  if (session.status === 'initializing') return <main className="foundation"><StatusBlock title="正在恢复会话…" /></main>
  if (session.status !== 'authenticated') return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}

/** @param {{title: string, description: string}} props */
export function FoundationPage({ title, description }) {
  return <><p className="eyebrow">我的寝室生活</p><h1>{title}</h1><p className="page-description">{description}</p>
    <StatusBlock title="功能准备中"><p>该功能尚未开放，请稍后再来。</p></StatusBlock></>
}

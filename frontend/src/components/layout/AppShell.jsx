import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { House, List, DoorOpen, Bell, User } from 'lucide-react'
import { useSession } from '../../features/auth/SessionProvider.jsx'
import { Modal } from '../Modal.jsx'
import { StatusBlock } from '../feedback/StatusBlock.jsx'
import { AccountContent } from '../../features/auth/AccountContent.jsx'
import { RoomsBootstrap } from '../../features/rooms/RoomsBootstrap.jsx'

const pages = [
  { path: '/overview', label: '用电总览', icon: House },
  { path: '/details', label: '电费明细', icon: List },
  { path: '/rooms', label: '我的寝室', icon: DoorOpen },
  { path: '/monitor', label: '监控提醒', icon: Bell },
]

export function AppShell() {
  const { user } = useSession()
  const [accountOpen, setAccountOpen] = useState(false)
  return <div className="app-shell">
    <aside className="sidebar"><span className="brand">ELECT · 寝室电力</span>
      <p className="nav-caption">照顾日常用电</p>
      <nav aria-label="主导航">{pages.map(({ path, label, icon }) => { const Icon = icon; return <NavLink key={path} to={path}>
        <Icon size={20} aria-hidden="true" />{label}</NavLink> })}</nav>
      <p className="sidebar-note">寝室用电，心中有数。</p>
    </aside>
    <div className="workspace"><header className="topbar"><span className="mobile-brand">寝室电力</span>
      <button className="account-button" onClick={() => setAccountOpen(true)}><User size={18} aria-hidden="true" />我的账户</button>
    </header><main id="main-content" className="page-content"><RoomsBootstrap />
      {user?.credential_status === 'requires_reauth' && <StatusBlock title="学校认证需要修复"
        action={{ label: '重新认证', onClick: () => setAccountOpen(true) }}><p>你仍可查看已有记录。</p></StatusBlock>}
      <Outlet /></main></div>
    <Modal open={accountOpen} title="我的账户" onClose={() => setAccountOpen(false)}>
      <AccountContent onClose={() => setAccountOpen(false)} />
    </Modal>
  </div>
}

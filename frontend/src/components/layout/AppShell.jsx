import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { LayoutDashboard, Wallet, Building2, Bell, User, ChevronRight, LogOut } from 'lucide-react'
import { useSession } from '../../features/auth/SessionProvider.jsx'
import { Modal } from '../Modal.jsx'
import { StatusBlock } from '../feedback/StatusBlock.jsx'
import { AccountContent } from '../../features/auth/AccountContent.jsx'
import { RoomsBootstrap } from '../../features/rooms/RoomsBootstrap.jsx'
import { useBindings } from '../../features/rooms/useBindings.js'
import { Brand } from './Brand.jsx'

const pages = [
  { path: '/overview', label: '总览', icon: LayoutDashboard },
  { path: '/details', label: '电费明细', icon: Wallet },
  { path: '/rooms', label: '选择与绑定', icon: Building2 },
  { path: '/monitor', label: '监控与预警', icon: Bell },
]

export function AppShell() {
  const { profile, profileStatus, refreshUser } = useSession()
  const { pathname } = useLocation()
  const bindings = useBindings({ pageSize: 100 })
  const room = bindings.data?.items.find(item => item.id === bindings.data.default_binding_id)
  const title = pages.find(page => pathname.startsWith(page.path))?.label ?? '寝室详情'
  const [accountOpen, setAccountOpen] = useState(false)
  return <div className="app-shell">
    <aside className="sidebar"><Brand />
      <nav aria-label="主导航">{pages.map(({ path, label, icon }) => { const Icon = icon; return <NavLink key={path} to={path}>
        <Icon size={19} aria-hidden="true" />{label}<span className="nav-active-dot" /></NavLink> })}</nav>
      <div className="sidebar-bottom"><button className="sidebar-profile" aria-label="我的账户" onClick={() => setAccountOpen(true)}>
        <span className="avatar">同</span><span className="profile-identity"><strong>{profile?.student_id ?? '学校资料暂不可用'}</strong><small>在校学生</small></span>
        <LogOut className="profile-icon" size={18} aria-hidden="true" /><User className="mobile-account" size={16} aria-hidden="true" /><span className="mobile-account">我的账户</span></button></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="breadcrumb">我的用电空间<ChevronRight size={14} aria-hidden="true" /><strong>{title}</strong></div>
      <span className="top-room"><Building2 size={15} aria-hidden="true" />{room?.display_name ?? (bindings.data?.default_binding_id ? '默认寝室信息暂不可用' : '尚未设置默认寝室')}</span>
    </header><main id="main-content" className="page-content"><RoomsBootstrap />
      {profileStatus === 'unavailable' && <StatusBlock title="学校资料暂不可用"
        action={{ label: '重新加载学校资料', onClick: () => { void refreshUser() } }}><p>仍可查看已有记录和关闭监控，学校相关操作暂不可用。</p></StatusBlock>}
      {profile?.credential_status === 'requires_reauth' && <StatusBlock title="学校认证需要修复"
        action={{ label: '重新认证', onClick: () => setAccountOpen(true) }}><p>你仍可查看已有记录。</p></StatusBlock>}
      <Outlet /></main></div>
    <Modal open={accountOpen} title="我的账户" onClose={() => setAccountOpen(false)}>
      <AccountContent onClose={() => setAccountOpen(false)} />
    </Modal>
  </div>
}

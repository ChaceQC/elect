import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthGuard, FoundationPage } from './router.jsx'
import { AppShell } from '../components/layout/AppShell.jsx'
import { LoginPage } from '../features/auth/LoginPage.jsx'
import { RoomsPage } from '../features/rooms/RoomsPage.jsx'

export default function App() {
  return <><a className="skip-link" href="#main-content">跳到正文</a><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<AuthGuard />}><Route element={<AppShell />}>
      <Route index element={<Navigate to="/overview" replace />} />
      <Route path="/overview" element={<FoundationPage title="用电总览" description="了解寝室余额和最近的用电情况。" />} />
      <Route path="/details" element={<FoundationPage title="电费明细" description="按日期查看消费趋势与采集记录。" />} />
      <Route path="/rooms" element={<RoomsPage />} />
      <Route path="/monitor" element={<FoundationPage title="监控提醒" description="设置采集间隔和低余额提醒。" />} />
    </Route></Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></>
}

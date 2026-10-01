import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthGuard } from './router.jsx'
import { AppShell } from '../components/layout/AppShell.jsx'
import { LoginPage } from '../features/auth/LoginPage.jsx'
import { RoomsPage } from '../features/rooms/RoomsPage.jsx'
import { MonitorPage } from '../features/monitoring/MonitorPage.jsx'
import { RoomView } from '../features/rooms/RoomView.jsx'
import { OverviewPage } from '../features/history/OverviewPage.jsx'
import { HistoryPage } from '../features/history/HistoryPage.jsx'

export default function App() {
  return <><a className="skip-link" href="#main-content">跳到正文</a><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<AuthGuard />}><Route element={<AppShell />}>
      <Route index element={<Navigate to="/overview" replace />} />
      <Route path="/overview" element={<OverviewPage />} />
      <Route path="/details" element={<HistoryPage />} />
      <Route path="/rooms" element={<RoomsPage />} />
      <Route path="/rooms/:bindingId" element={<RoomView />} />
      <Route path="/monitor" element={<MonitorPage />} />
    </Route></Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></>
}

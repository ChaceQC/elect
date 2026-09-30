import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './app/App.jsx'
import { BrowserRouter } from 'react-router-dom'
import { AppProviders } from './app/providers.jsx'
import './styles/base.css'

const root = document.getElementById('app')
if (!root) throw new Error('缺少应用挂载节点')
async function mount() {
  if (import.meta.env.DEV && import.meta.env.VITE_ENABLE_MSW === 'true') {
    const { startMocks } = await import('./mocks/browser.js')
    await startMocks()
  }
  createRoot(/** @type {HTMLElement} */ (root)).render(<StrictMode><BrowserRouter>
    <AppProviders><App /></AppProviders>
  </BrowserRouter></StrictMode>)
}
void mount()

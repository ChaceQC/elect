import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './app/App.jsx'
import './styles/base.css'

const root = document.getElementById('app')
if (!root) throw new Error('缺少应用挂载节点')
createRoot(root).render(<StrictMode><App /></StrictMode>)

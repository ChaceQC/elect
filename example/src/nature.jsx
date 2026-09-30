import { createRoot } from 'react-dom/client'
import StudentApp from './StudentApp.jsx'
import './student.css'
import './blue.css'
document.documentElement.dataset.theme = 'blue'
createRoot(document.getElementById('app')).render(<div className="blue-preview"><StudentApp compact /></div>)

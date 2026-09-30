import { createContext, useContext, useEffect, useState } from 'react'

const ToastContext = createContext(/** @type {((message: string)=>void)|null} */ (null))
/** @param {{children: import('react').ReactNode}} props */
export function ToastProvider({ children }) {
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (!message) return
    const timer = setTimeout(() => setMessage(''), 4000)
    return () => clearTimeout(timer)
  }, [message])
  return <ToastContext.Provider value={setMessage}>{children}
    {message && <div className="toast" role="status">{message}</div>}
  </ToastContext.Provider>
}
export function useToast() {
  const toast = useContext(ToastContext)
  if (!toast) throw new Error('缺少提示上下文')
  return toast
}

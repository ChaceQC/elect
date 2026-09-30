import { useState } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createQueryClient } from './queryClient.js'
import { SessionProvider } from '../features/auth/SessionProvider.jsx'
import { ToastProvider } from '../components/feedback/Toast.jsx'

/** @param {{children: import('react').ReactNode}} props */
export function AppProviders({ children }) {
  const [queryClient] = useState(createQueryClient)
  return <QueryClientProvider client={queryClient}>
    <SessionProvider><ToastProvider>{children}</ToastProvider></SessionProvider>
  </QueryClientProvider>
}

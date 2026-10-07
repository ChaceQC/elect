import { createContext, useMemo } from 'react'
import { useSession } from '../auth/SessionProvider.jsx'

export const QueryRefreshContext = createContext(/** @type {Set<string>|null} */ (null))

/** @param {{children: import('react').ReactNode}} props */
export function QueryRefreshProvider({ children }) {
  const { user } = useSession()
  // 导航、日期和粒度切换共享本轮记录；重新登录或浏览器重载开始新一轮。
  const attempted = useMemo(() => user ? new Set() : null, [user])
  return <QueryRefreshContext.Provider value={attempted}>{children}</QueryRefreshContext.Provider>
}

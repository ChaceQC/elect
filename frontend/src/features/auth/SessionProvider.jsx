import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { clearRecovery } from '../../api/intents.js'

/** @typedef {import('../../api/generated').components['schemas']['Me']} Me */
/** @typedef {{status: 'initializing'|'authenticated'|'signed_out'|'unavailable', user: Me|null,
 * error: ApiError|null}} SessionState */
/** @typedef {SessionState & {initialize: ()=>Promise<void>, acceptUser: (user: Me|null)=>Promise<void>,
 * endSession: ()=>Promise<void>}} SessionContextValue */
const SessionContext = createContext(/** @type {SessionContextValue|null} */ (null))

/** @param {unknown} input @returns {Me} */
function parseSession(input) {
  const value = /** @type {Me} */ (input)
  if (!value || typeof value.id !== 'string' || !/^[0-9a-f-]{36}$/i.test(value.id) ||
    typeof value.csrf_token !== 'string' || !value.csrf_token || typeof value.school !== 'string' ||
    typeof value.student_id !== 'string' || !value.consent ||
    !['active', 'requires_reauth', 'revoking', 'revoked', 'missing'].includes(value.credential_status)) {
    throw new ApiError('INVALID_RESPONSE', '无法识别当前会话，请重新检查', 200)
  }
  return value
}

/** @param {{children: import('react').ReactNode}} props */
export function SessionProvider({ children }) {
  const queryClient = useQueryClient()
  const [state, setState] = useState(/** @type {SessionState} */ ({ status: 'initializing', user: null, error: null }))
  const currentUser = useRef(/** @type {Me|null} */ (null))
  const sequence = useRef(0)
  const pending = useRef(/** @type {AbortController|null} */ (null))

  const acceptUser = useCallback(/** @param {Me|null} user */ async (user) => {
    const generation = ++sequence.current
    pending.current?.abort()
    const previous = currentUser.current?.id
    apiClient.reset()
    setState({ status: 'initializing', user: null, error: null })
    await queryClient.cancelQueries()
    if (generation !== sequence.current) return
    queryClient.clear()
    if (previous && previous !== user?.id) clearRecovery(previous)
    currentUser.current = user
    apiClient.csrfToken = user?.csrf_token ?? null
    setState({ status: user ? 'authenticated' : 'signed_out', user, error: null })
  }, [queryClient])

  const endSession = useCallback(() => acceptUser(null), [acceptUser])
  const initialize = useCallback(async () => {
    const request = ++sequence.current
    pending.current?.abort()
    pending.current = new AbortController()
    setState({ status: 'initializing', user: null, error: null })
    try {
      const result = await apiClient.request('/auth/me', { signal: pending.current.signal })
      if (request === sequence.current) await acceptUser(parseSession(result.data))
    } catch (error) {
      if (request !== sequence.current || (error instanceof DOMException && error.name === 'AbortError')) return
      if (error instanceof ApiError && error.code === 'APP_SESSION_EXPIRED') {
        await endSession()
      } else {
        setState({ status: 'unavailable', user: null,
          error: error instanceof ApiError ? error : new ApiError('NETWORK_ERROR', '无法恢复会话', 0) })
      }
    }
  }, [acceptUser, endSession])

  useEffect(() => {
    apiClient.onSessionExpired = () => { void endSession() }
    void initialize()
    const counter = sequence
    const request = pending
    return () => { ++counter.current; request.current?.abort(); apiClient.onSessionExpired = null }
  }, [initialize, endSession])
  return <SessionContext.Provider value={{ ...state, initialize, acceptUser, endSession }}>{children}</SessionContext.Provider>
}

export function useSession() {
  const session = useContext(SessionContext)
  if (!session) throw new Error('缺少会话上下文')
  return session
}

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { clearRecovery } from '../../api/intents.js'
import { parseLocal, parseProfile } from './sessionData.js'

/** @typedef {import('../../api/generated').components['schemas']['Me']} Me */
/** @typedef {import('../../api/generated').components['schemas']['LocalSession']} LocalSession */
/** @typedef {{status: 'initializing'|'authenticated'|'signed_out'|'unavailable', user: LocalSession|null,
 * error: ApiError|null, profile: Me|null, profileStatus: 'idle'|'loading'|'ready'|'unavailable'}} SessionState */
/** @typedef {SessionState & {initialize: ()=>Promise<void>, acceptUser: (user: Me|null)=>Promise<void>,
 * endSession: ()=>Promise<void>, refreshUser: ()=>Promise<void>}} SessionContextValue */
const SessionContext = createContext(/** @type {SessionContextValue|null} */ (null))

const emptyProfile = /** @type {const} */ ({ profile: null, profileStatus: 'idle' })

/** @param {{children: import('react').ReactNode}} props */
export function SessionProvider({ children }) {
  const queryClient = useQueryClient()
  const [state, setState] = useState(/** @type {SessionState} */ ({ status: 'initializing', user: null, error: null, ...emptyProfile }))
  const currentUser = useRef(/** @type {LocalSession|null} */ (null))
  const legacy = useRef(false)
  const sequence = useRef(0)
  const refreshSequence = useRef(0)
  const pending = useRef(/** @type {AbortController|null} */ (null))
  const channel = useRef(/** @type {BroadcastChannel|null} */ (null))

  const acceptIdentity = useCallback(/** @param {LocalSession|null} user @param {Me|null} profile @param {boolean} announce */ async (user, profile, announce) => {
    const generation = ++sequence.current
    pending.current?.abort()
    const previous = currentUser.current?.id
    apiClient.reset()
    setState({ status: 'initializing', user: null, error: null, ...emptyProfile })
    await queryClient.cancelQueries()
    if (generation !== sequence.current) return
    queryClient.clear()
    if (previous && previous !== user?.id) clearRecovery(previous)
    currentUser.current = user
    apiClient.csrfToken = user?.csrf_token ?? null
    setState({ status: user ? 'authenticated' : 'signed_out', user, error: null,
      profile, profileStatus: profile ? 'ready' : user ? 'loading' : 'idle' })
    if (announce) channel.current?.postMessage('session-changed')
  }, [queryClient])

  const acceptUser = useCallback(/** @param {Me|null} value */ async value => {
    const profile = value ? parseProfile(value) : null
    await acceptIdentity(profile ? parseLocal(profile) : null, profile, true)
  }, [acceptIdentity])

  const endSession = useCallback(() => acceptUser(null), [acceptUser])
  const refreshUser = useCallback(async () => {
    const request = sequence.current
    const refresh = ++refreshSequence.current
    const expected = currentUser.current?.id
    if (!expected) return
    try {
      const result = await apiClient.request('/auth/me')
      if (request !== sequence.current || refresh !== refreshSequence.current) return
      const profile = parseProfile(result.data)
      if (profile.id !== expected) throw new ApiError('INVALID_RESPONSE', '学校资料与当前账户不一致', 200)
      // CSRF与身份始终来自已验证的本地会话，资料响应不能切换当前账户。
      setState(previous => ({ ...previous, profile, profileStatus: 'ready' }))
    } catch (error) {
      if (request !== sequence.current || refresh !== refreshSequence.current) return
      if (error instanceof ApiError && error.status === 401) await acceptIdentity(null, null, false)
      else setState(previous => ({ ...previous, profile: null, profileStatus: 'unavailable' }))
    }
  }, [acceptIdentity])
  const initialize = useCallback(async () => {
    const request = ++sequence.current
    pending.current?.abort()
    pending.current = new AbortController()
    setState({ status: 'initializing', user: null, error: null, ...emptyProfile })
    try {
      let result
      try {
        result = await apiClient.request(legacy.current ? '/auth/me' : '/auth/session', { signal: pending.current.signal })
      } catch (error) {
        if (request !== sequence.current) return
        if (legacy.current || !(error instanceof ApiError) || error.status !== 404) throw error
        legacy.current = true
        result = await apiClient.request('/auth/me', { signal: pending.current.signal })
      }
      if (request !== sequence.current) return
      const profile = legacy.current ? parseProfile(result.data) : null
      await acceptIdentity(parseLocal(result.data), profile, false)
      if (!profile) void refreshUser()
    } catch (error) {
      if (request !== sequence.current || (error instanceof DOMException && error.name === 'AbortError')) return
      if (error instanceof ApiError && error.status === 401) {
        await acceptIdentity(null, null, false)
      } else {
        setState({ status: 'unavailable', user: null, ...emptyProfile,
          error: error instanceof ApiError ? error : new ApiError('NETWORK_ERROR', '无法恢复会话', 0) })
      }
    }
  }, [acceptIdentity, refreshUser])

  useEffect(() => {
    const events = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('elect-session')
    channel.current = events
    if (events) events.onmessage = event => {
      if (event.data !== 'session-changed') return
      void acceptIdentity(null, null, false).then(initialize)
    }
    apiClient.onSessionExpired = () => { if (currentUser.current) void endSession() }
    void initialize()
    const counter = sequence
    const request = pending
    return () => {
      ++counter.current; request.current?.abort(); apiClient.onSessionExpired = null
      events?.close(); channel.current = null
    }
  }, [initialize, endSession, acceptIdentity])
  useEffect(() => {
    const check = () => {
      if (document.visibilityState !== 'hidden' && currentUser.current) void refreshUser().catch(() => {})
    }
    window.addEventListener('focus', check)
    document.addEventListener('visibilitychange', check)
    return () => {
      window.removeEventListener('focus', check)
      document.removeEventListener('visibilitychange', check)
    }
  }, [refreshUser])
  return <SessionContext.Provider value={{ ...state, initialize, acceptUser, endSession, refreshUser }}>{children}</SessionContext.Provider>
}

export function useSession() {
  const session = useContext(SessionContext)
  if (!session) throw new Error('缺少会话上下文')
  return session
}

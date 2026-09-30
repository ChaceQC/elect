import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { readOperation, isTerminal, pollInterval } from '../api/operations.js'
import { operationKey } from '../app/queryKeys.js'
import { useSession } from '../features/auth/SessionProvider.jsx'

/** @param {import('../api/intents.js').ResourceKind} kind @param {string|null} id
 * @param {(data: import('../api/operations.js').OperationResource)=>void} [onTerminal] */
export function useOperation(kind, id, onTerminal) {
  const { user } = useSession()
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden')
  const started = useRef({ id, time: Date.now() })
  if (started.current.id !== id) started.current = { id, time: Date.now() }
  const notified = useRef(new Set())
  useEffect(() => {
    const change = () => setVisible(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', change)
    return () => document.removeEventListener('visibilitychange', change)
  }, [])
  const query = useQuery({
    queryKey: operationKey(user?.id ?? '', kind, id),
    queryFn: ({ signal }) => readOperation(kind, /** @type {string} */ (id), signal),
    enabled: Boolean(user && id && visible), staleTime: 0,
    refetchInterval: (query) => pollInterval(kind, query.state.data?.state,
      Date.now() - started.current.time, visible),
    refetchIntervalInBackground: false,
  })
  useEffect(() => {
    const key = `${user?.id}:${kind}:${id}`
    if (query.data && isTerminal(kind, query.data.state) && !notified.current.has(key)) {
      notified.current.add(key); onTerminal?.(query.data)
    }
  }, [user?.id, kind, id, query.data, onTerminal])
  return { ...query, refresh: query.refetch }
}

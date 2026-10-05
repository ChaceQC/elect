import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { readOperation, isTerminal, pollInterval } from '../api/operations.js'
import { operationKey } from '../app/queryKeys.js'
import { useSession } from '../features/auth/SessionProvider.jsx'
import { usePollingWindow } from './usePollingWindow.js'

/** @param {import('../api/intents.js').ResourceKind} kind @param {string|null} id
 * @param {(data: import('../api/operations.js').OperationResource)=>void} [onTerminal] */
export function useOperation(kind, id, onTerminal) {
  const { user } = useSession()
  const polling = usePollingWindow(`${user?.id}:${kind}:${id}`)
  const notified = useRef(new Set())
  const query = useQuery({
    queryKey: operationKey(user?.id ?? '', kind, id),
    queryFn: ({ signal }) => readOperation(kind, /** @type {string} */ (id), signal),
    enabled: Boolean(user && id && polling.visible), staleTime: 0,
    refetchInterval: (query) => pollInterval(kind, query.state.data?.state,
      polling.elapsed(), polling.visible, query.state.data?.type),
    refetchIntervalInBackground: false,
  })
  useEffect(() => {
    const key = `${user?.id}:${kind}:${id}`
    if (query.data && isTerminal(kind, query.data.state) && !notified.current.has(key)) {
      notified.current.add(key); onTerminal?.(query.data)
    }
  }, [user?.id, kind, id, query.data, onTerminal])
  const refresh = () => { polling.restart(); return query.refetch() }
  return { ...query, refresh, pollingPaused: !!id && query.data?.type !== 'unbind_room' && !isTerminal(kind, query.data?.state) && polling.paused }
}

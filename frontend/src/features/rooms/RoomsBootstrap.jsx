import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useBindings } from './useBindings.js'
import { useRequestIntent } from '../../hooks/useRequestIntent.js'
import { useSession } from '../auth/SessionProvider.jsx'

export function RoomsBootstrap() {
  const { user, profile } = useSession()
  const query = useBindings()
  const cache = useQueryClient()
  const { controller, submit } = useRequestIntent()
  const tried = useRef(/** @type {string|null} */ (null))
  useEffect(() => {
    if (!user || !profile || !controller || tried.current === user.id || !query.data) return
    tried.current = user.id
    if (query.data.sync_status !== 'loading' || query.data.last_synced_at || query.data.pending_operations.length) return
    const previous = controller.restore().find(item => item.path === '/room-bindings/sync' && !item.id)
    const intent = previous ?? controller.create('/room-bindings/sync')
    void submit(intent).catch(() => {}).finally(() => { void cache.invalidateQueries({ queryKey: ['bindings', user.id] }) })
  }, [user, profile, controller, submit, query.data, cache])
  return null
}

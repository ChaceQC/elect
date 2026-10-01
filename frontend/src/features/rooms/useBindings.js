import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { useSession } from '../auth/SessionProvider.jsx'

/** @typedef {import('../../api/generated').components['schemas']['Bindings']} Bindings */
/** @param {{q?: string, page?: number, pageSize?: number}} [options] */
export function useBindings({ q = '', page = 1, pageSize = 10 } = {}) {
  const { user } = useSession()
  return useQuery({ queryKey: ['bindings', user?.id, { q, page, pageSize }], enabled: !!user,
    queryFn: async ({ signal }) => /** @type {Bindings} */ ((await apiClient.request(`/room-bindings?${new URLSearchParams({
      q, page: String(page), page_size: String(pageSize) })}`, { signal })).data),
    refetchInterval: (query) => query.state.data?.sync_status === 'loading' ||
      query.state.data?.pending_operations.some(item => ['accepted', 'running'].includes(item.state)) ? 2000 : false,
  })
}

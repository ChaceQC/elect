import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client.js'
import { useSession } from '../auth/SessionProvider.jsx'

/** @param {string} bindingId */
export function usePaymentCapability(bindingId) {
  const { user, profile } = useSession()
  const query = useQuery({ queryKey: ['payment-capabilities', user?.id, bindingId], enabled: !!user && !!profile, retry: false,
    staleTime: 30_000, refetchOnWindowFocus: true,
    queryFn: async ({ signal }) => /** @type {import('../../api/generated').components['schemas']['Capabilities']} */ (
      (await apiClient.request(`/payments/capabilities?binding_id=${bindingId}`, { signal })).data) })
  return { ...query, data: profile ? query.data : undefined, profileAvailable: !!profile }
}

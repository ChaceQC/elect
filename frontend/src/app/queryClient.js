import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client.js'

export function createQueryClient() {
  return new QueryClient({ defaultOptions: {
    queries: {
      staleTime: 30_000, gcTime: 300_000, refetchOnWindowFocus: false,
      retry: (failures, error) => failures < 2 && error instanceof ApiError && error.retryable &&
        [0, 429, 502, 503, 504].includes(error.status),
      retryDelay: (attempt, error) => error instanceof ApiError && error.retryAfterSeconds !== null
        ? error.retryAfterSeconds * 1000 : Math.min(1000 * 2 ** attempt, 10_000),
    },
    mutations: { retry: false },
  } })
}

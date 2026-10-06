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
      query.state.data?.default_switch_operation_id ||
      query.state.data?.binding_removal_operation_id ||
      query.state.data?.pending_operations.some(item => ['accepted', 'running', 'reconciling'].includes(item.state)) ? 2000 : false,
  })
}

/** @param {Bindings|undefined} data @param {import('../auth/SessionProvider.jsx').Me|null} user */
export function bindingUnavailableReason(data, user) {
  if (!user) return '学校资料暂不可用，绑定和解绑暂不可用。'
  if (!data) return '正在确认学校绑定是否开放'
  if (!data.binding_write_enabled) return '新增和删除学校绑定暂未开放，仍可同步和查看已有寝室。'
  if (user?.credential_status !== 'active' || !user.consent.credential_use_allowed) return '请在“我的账户”中重新学校认证后绑定或解绑。'
  return ''
}

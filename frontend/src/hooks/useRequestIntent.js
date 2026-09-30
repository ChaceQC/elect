import { useMemo, useState } from 'react'
import { OperationController } from '../api/intents.js'
import { useSession } from '../features/auth/SessionProvider.jsx'

export function useRequestIntent() {
  const { user } = useSession()
  const controller = useMemo(() => user ? new OperationController(user.id) : null, [user])
  const [busy, setBusy] = useState(false)
  /** @param {import('../api/intents.js').Intent} intent */
  async function submit(intent) {
    if (!controller) throw new Error('请先登录')
    setBusy(true)
    try { return await controller.submit(intent) } finally { setBusy(false) }
  }
  return { controller, submit, busy }
}

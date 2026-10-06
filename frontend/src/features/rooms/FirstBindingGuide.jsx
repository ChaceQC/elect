import { Building2, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { bindingUnavailableReason, useBindings } from './useBindings.js'
import { useSession } from '../auth/SessionProvider.jsx'

export function FirstBindingGuide() {
  const { profile } = useSession()
  const query = useBindings()
  const reason = bindingUnavailableReason(query.data, profile)
  return <section className="first-bind"><span className="large-icon"><Building2 size={38} aria-hidden="true" /></span>
    <h1>先找到你的寝室</h1>{reason ? <><p role="status">{reason}</p><Link to="/rooms">查看学校绑定</Link></> : <Link className="button-link" to="/rooms?bind=1"><Plus size={17} aria-hidden="true" />绑定我的寝室</Link>}
  </section>
}

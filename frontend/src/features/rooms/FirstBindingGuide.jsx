import { Building2, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

export function FirstBindingGuide() {
  return <section className="first-bind"><span className="large-icon"><Building2 size={38} aria-hidden="true" /></span>
    <h1>先找到你的寝室</h1><Link className="button-link" to="/rooms?bind=1"><Plus size={17} aria-hidden="true" />绑定我的寝室</Link>
  </section>
}

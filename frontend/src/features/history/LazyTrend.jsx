import { lazy, Suspense } from 'react'

const Chart = lazy(() => import('./ConsumptionTrend.jsx').then(module => ({ default: module.ConsumptionTrend })))
/** @param {{buckets: import('../../api/generated').components['schemas']['Bucket'][]}} props */
export function ConsumptionTrend(props) {
  return <Suspense fallback={<p role="status">正在加载图表…</p>}><Chart {...props} /></Suspense>
}

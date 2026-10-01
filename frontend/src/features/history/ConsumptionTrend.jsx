import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { moneyLabel } from '../../lib/money.js'

echarts.use([LineChart, AriaComponent, GridComponent, TooltipComponent, CanvasRenderer])
/** @typedef {import('../../api/generated').components['schemas']['Bucket']} Bucket */
/** @param {{buckets: Bucket[]}} props */
export function ConsumptionTrend({ buckets }) {
  const element = useRef(/** @type {HTMLDivElement|null} */ (null))
  const chart = useRef(/** @type {ReturnType<typeof echarts.init>|null} */ (null))
  useEffect(() => {
    if (!element.current) return
    const instance = echarts.init(element.current)
    chart.current = instance
    const resize = () => instance.resize()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    observer?.observe(element.current)
    window.addEventListener('resize', resize)
    return () => { observer?.disconnect(); window.removeEventListener('resize', resize); instance.dispose(); chart.current = null }
  }, [])
  useEffect(() => {
    chart.current?.setOption({ animation: false, aria: { enabled: true, label: { description: '学校消费记录趋势，未知日期保留断点' } }, grid: { left: 45, right: 18, top: 24, bottom: 45 },
      tooltip: { trigger: 'axis', formatter: (/** @type {any} */ params) => {
        const bucket = buckets[Array.isArray(params) ? params[0]?.dataIndex : params.dataIndex]
        return bucket ? `${bucket.start_date} 至 ${bucket.end_date}<br/>学校记录金额：${moneyLabel(bucket.amount)}<br/>已知 ${bucket.known_days}/${bucket.expected_days} 天${bucket.complete ? '' : '（部分数据）'}` : ''
      } }, xAxis: { type: 'category', data: buckets.map(b => b.start_date), axisLabel: { hideOverlap: true } },
      yAxis: { type: 'value', name: '元', min: 'dataMin' }, series: [{ type: 'line', connectNulls: false, showSymbol: true,
        symbolSize: 7, lineStyle: { width: 3, color: '#3493bc' }, itemStyle: { color: '#3493bc' },
        data: buckets.map(b => b.amount === null ? null : Number(b.amount)) }] }, { notMerge: true })
  }, [buckets])
  return <><div ref={element} className="consumption-chart" role="img" aria-label="学校消费记录趋势，未知日期保留断点" />
    <details className="chart-data"><summary>查看图表数据</summary><ul>{buckets.map(bucket => <li key={bucket.start_date}>
      {bucket.start_date} 至 {bucket.end_date}：{moneyLabel(bucket.amount)} · 已知{bucket.known_days}/{bucket.expected_days}天{bucket.complete ? '' : '，部分数据'}</li>)}</ul></details>
  </>
}

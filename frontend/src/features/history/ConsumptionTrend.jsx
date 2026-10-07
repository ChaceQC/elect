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
  const hasEstimates = buckets.some(bucket => bucket.estimated_amount != null)
  const description = hasEstimates ? '消费趋势，含余额变化估算，未知日期保留断点' : '学校消费记录趋势，未知日期保留断点'
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
    chart.current?.setOption({ animation: false, textStyle: { fontFamily: 'Inter, Segoe UI, Microsoft YaHei, sans-serif', color: '#85958f' }, aria: { enabled: true, label: { description } }, grid: { left: 42, right: 20, top: 36, bottom: 30 },
      tooltip: { trigger: 'axis', formatter: (/** @type {any} */ params) => {
        const bucket = buckets[Array.isArray(params) ? params[0]?.dataIndex : params.dataIndex]
        return bucket ? `${bucket.start_date} 至 ${bucket.end_date}<br/>${bucket.estimated_amount != null ? '消费金额' : '学校记录金额'}：${moneyLabel(bucket.amount)}${bucket.estimated_amount != null ? `<br/>含余额变化估算：${moneyLabel(bucket.estimated_amount)}（${bucket.estimated_days}天）` : ''}<br/>已知 ${bucket.known_days}/${bucket.expected_days} 天${bucket.complete ? '' : bucket.known_days === 0 ? '（暂无数据）' : '（部分数据）'}` : ''
      } }, xAxis: { type: 'category', boundaryGap: false, data: buckets.map(b => b.start_date), axisLabel: { hideOverlap: true, fontSize: 10, formatter: (/** @type {string} */ value) => value.slice(5).replace('-', '/') }, axisLine: { lineStyle: { color: '#e5ebe7' } }, axisTick: { show: false } },
      yAxis: { type: 'value', name: '消费 / 元', min: (/** @type {{min: number}} */ value) => Math.min(0, value.min), axisLabel: { fontSize: 11 }, splitLine: { lineStyle: { type: 'dashed', color: '#eaf0ed' } } }, series: [{ type: 'line', smooth: true, connectNulls: false, showSymbol: buckets.length <= 14,
        symbolSize: 6, lineStyle: { width: 3, color: '#579ed6' }, itemStyle: { color: '#579ed6' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#b9ddf5aa' }, { offset: 1, color: '#f4f9ff00' }]) },
        data: buckets.map(b => b.amount === null ? null : Number(b.amount)) }] }, { notMerge: true })
  }, [buckets, description])
  return <><div ref={element} className="consumption-chart" role="img" aria-label={description} />
    {hasEstimates && <p className="muted">含余额变化估算，充值等变化可能导致偏差；当天首次余额减少计入前一天。</p>}
    <details className="chart-data"><summary>查看图表数据</summary><ul>{buckets.map(bucket => <li key={bucket.start_date}>
      {bucket.start_date} 至 {bucket.end_date}：{moneyLabel(bucket.amount)}{bucket.estimated_amount != null && `（含余额变化估算 ${moneyLabel(bucket.estimated_amount)}）`} · 已知{bucket.known_days}/{bucket.expected_days}天{bucket.complete ? '' : bucket.known_days === 0 ? '，暂无数据' : '，部分数据'}</li>)}</ul></details>
  </>
}

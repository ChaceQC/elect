import Chart from './Chart.jsx'
const money = value => Number(value).toFixed(2)
export default function Trend({ points }) {
  const theme = getComputedStyle(document.documentElement)
  const values = points ? points.map(point => point.value) : [3.2, 4.5, 3.8, 5.9, 4.7, 3.5, 4.2, 5.3, 4.1, 3.7, 4.8, 3.6, 4.4, 3.9]
  const labels = points ? points.map(point => point.label) : values.map((_, i) => `09/${17 + i}`)
  return <Chart style={{ height: 280, width: '100%' }} option={{ animationDuration: 500, grid: { left: 42, right: 20, top: 35, bottom: 32 }, tooltip: { trigger: 'axis', valueFormatter: v => `¥ ${money(v)}` }, xAxis: { type: 'category', boundaryGap: false, data: labels, axisLine: { lineStyle: { color: '#e8ece7' } }, axisTick: { show: false }, axisLabel: { color: '#8a948f', fontSize: 11 } }, yAxis: { type: 'value', name: '消费 / 元', nameTextStyle: { color: '#8a948f' }, splitLine: { lineStyle: { color: '#edf0eb', type: 'dashed' } }, axisLabel: { color: '#8a948f' } }, series: [{ type: 'line', smooth: true, data: values, symbolSize: 6, itemStyle: { color: theme.getPropertyValue('--trend-color').trim() || '#387b5c' }, lineStyle: { width: 3 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: theme.getPropertyValue('--trend-fill').trim() || '#c8deceaa' }, { offset: 1, color: theme.getPropertyValue('--trend-fade').trim() || '#f9fbf600' }] } } }] }} />
}

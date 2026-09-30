import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export default function Chart({ option, style }) {
  const ref = useRef(null)
  useEffect(() => {
    const chart = echarts.init(ref.current)
    chart.setOption(option)
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(ref.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [option])
  return <div ref={ref} style={style} />
}

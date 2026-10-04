import { useEffect, useRef, useState } from 'react'

export const POLLING_WINDOW_MS = 120_000

/** @param {string} key */
export function usePollingWindow(key) {
  const started = useRef({ key, time: Date.now() })
  if (started.current.key !== key) started.current = { key, time: Date.now() }
  const [revision, setRevision] = useState(0)
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden')
  useEffect(() => {
    const change = () => { setVisible(document.visibilityState !== 'hidden'); setRevision(value => value + 1) }
    document.addEventListener('visibilitychange', change)
    return () => document.removeEventListener('visibilitychange', change)
  }, [])
  useEffect(() => {
    const remaining = POLLING_WINDOW_MS - (Date.now() - started.current.time)
    if (remaining <= 0) return
    const timer = setTimeout(() => setRevision(value => value + 1), remaining)
    return () => clearTimeout(timer)
  }, [key, revision])
  function restart() { started.current.time = Date.now(); setRevision(value => value + 1) }
  return { visible, paused: Date.now() - started.current.time >= POLLING_WINDOW_MS,
    elapsed: () => Date.now() - started.current.time, restart }
}

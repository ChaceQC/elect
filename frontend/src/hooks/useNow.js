import { useEffect, useState } from 'react'

export function useNow() {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    let timer = /** @type {ReturnType<typeof setInterval>|undefined} */ (undefined)
    const update = () => {
      clearInterval(timer)
      setNow(Date.now())
      if (document.visibilityState !== 'hidden') timer = setInterval(() => setNow(Date.now()), 1000)
    }
    update()
    document.addEventListener('visibilitychange', update)
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', update) }
  }, [])
  return now
}

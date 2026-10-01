/** @param {number} milliseconds @param {AbortSignal} signal */
export function abortableDelay(milliseconds, signal) {
  signal.throwIfAborted()
  return new Promise((accept, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('已停止等待', 'AbortError')) }
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); accept(null) }, milliseconds)
    signal.addEventListener('abort', abort, { once: true })
  })
}

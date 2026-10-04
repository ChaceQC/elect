/** @param {{paused: boolean, onResume: ()=>void, busy?: boolean}} props */
export function PollingNotice({ paused, onResume, busy = false }) {
  if (!paused) return null
  return <div role="status"><p>结果仍待确认，后台处理不受影响；已暂停自动刷新。</p>
    <button type="button" className="quiet" disabled={busy} onClick={onResume}>恢复自动更新</button></div>
}

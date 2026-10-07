import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ReceiptText, RefreshCw } from 'lucide-react'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { timestampLabel } from '../../lib/dates.js'
import { moneyLabel } from '../../lib/money.js'
import { useSession } from '../auth/SessionProvider.jsx'

/** @param {{bindingId: string, range: import('./DateRangePicker.jsx').Range}} props */
export function PaymentRecordsPanel({ bindingId, range }) {
  const { user, profile } = useSession()
  const [page, setPage] = useState(1)
  const [retryAt, setRetryAt] = useState(0)
  const available = profile?.credential_status === 'active' && profile.consent.credential_use_allowed
  const query = useQuery({ queryKey: ['payment-records', user?.id, bindingId, range],
    enabled: !!user && available, retry: false, staleTime: 60_000,
    refetchOnWindowFocus: false, refetchOnReconnect: false,
    queryFn: async ({ signal }) => {
      try {
        return /** @type {import('../../api/generated').components['schemas']['PaymentRecords']} */ ((await apiClient.request(`/room-bindings/${bindingId}/payment-records?${new URLSearchParams(range)}`, { signal, timeoutMs: 55_000 })).data)
      } catch (error) {
        setRetryAt(Date.now() + (error instanceof ApiError ? error.retryAfterSeconds ?? (error.status === 429 ? 60 : 0) : 0) * 1000)
        throw error
      }
    } })
  const records = query.data
  const currentPage = Math.min(page, Math.max(1, Math.ceil((records?.items.length ?? 0) / 10)))
  function refresh() {
    if (Date.now() < retryAt) return
    setPage(1)
    void query.refetch()
  }
  return <section className="card"><div className="card-heading"><div><h2>缴费明细列表</h2>
    {records && <p className="history-summary">总缴费 {moneyLabel(records.total_amount)}{!records.complete && ` · 已读取合计 ${moneyLabel(records.known_amount)}`}</p>}</div>
    <div className="actions">{records && <span className="pill">{records.total} 条</span>}<button className="icon-button" aria-label="读取最新缴费记录" title="读取最新缴费记录" aria-busy={query.isFetching} disabled={query.isFetching || !available} onClick={refresh}><RefreshCw size={16} className={query.isFetching ? 'refresh-spinning' : undefined} aria-hidden="true" /></button></div></div>
    {!available && <p role="status">学校认证可用后可查询缴费记录。</p>}
    {query.isFetching && !records && <p role="status">正在读取学校缴费记录…</p>}
    {query.error && <StatusBlock title={query.error.message} error action={{ label: '重新读取缴费记录', onClick: refresh }} />}
    {query.error instanceof ApiError && query.error.status === 429 && <p role="status">请求较频繁，请等待 {query.error.retryAfterSeconds ?? 60} 秒后重试。</p>}
    {records && <>
      {!records.complete && <p role="alert">学校记录尚未读取完整，总缴费暂不可用。请缩小日期范围或重新读取。</p>}
      {query.error && <p role="status">正在展示上次成功读取的记录。</p>}
      {!records.items.length && records.complete && <div className="empty"><ReceiptText size={29} /><p>所选范围内暂无学校已缴费记录。</p></div>}
      {!!records.items.length && <div className="table-scroll" tabIndex={0} role="region" aria-label="缴费明细数据表"><table className="samples-table"><caption className="sr-only">所选日期范围的学校已缴费记录</caption><thead><tr><th>缴费时间</th><th>实缴金额</th><th>支付方式</th><th>学校订单号</th></tr></thead>
        <tbody>{records.items.slice((currentPage - 1) * 10, currentPage * 10).map(item => <tr key={item.id}><td>{timestampLabel(item.paid_at)}{!item.paid_at && <small>创建于 {timestampLabel(item.created_at)}</small>}</td><td>{moneyLabel(item.amount)}</td><td>{item.method === '1' ? '微信' : item.method ? `其他（${item.method}）` : '—'}</td><td>{item.id}</td></tr>)}</tbody></table></div>}
      <div className="samples-footer"><p className="muted">学校记录 · 共 {records.total} 条</p><div className="pagination"><button className="quiet" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>上一页</button><span>第{currentPage}页</span><button className="quiet" disabled={currentPage * 10 >= records.items.length} onClick={() => setPage(currentPage + 1)}>下一页</button></div></div>
    </>}
  </section>
}

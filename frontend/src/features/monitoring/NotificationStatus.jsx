import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'

/** @param {string|null} value */
const when = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '暂无'
/** @param {{notification: import('../../api/generated').components['schemas']['NotificationSummary']}} props */
export function NotificationStatus({ notification }) {
  const states = { idle: '暂无发送', pending: '等待发送', sending: '发送中', sent: '邮件服务器已接收',
    email_failed: '发送失败', delivery_unknown: '投递结果未知', cancelled: '已取消' }
  return <section aria-label="邮件投递状态">
    <p>邮件状态：{states[notification.state]} · 正在处理 {notification.in_flight_count} 封</p>
    <p>最近服务器接收：{when(notification.last_sent_at)}</p>
    {notification.next_retry_at && <p>邮件下次重试：{when(notification.next_retry_at)}</p>}
    {notification.last_error_code && <p>最近邮件错误：{notification.last_error_code}</p>}
    {notification.state === 'email_failed' && <StatusBlock title="邮件发送失败" error>
      <p>请检查提醒邮箱或联系管理员。失败状态不会被显示为已送达。</p>
    </StatusBlock>}
    {notification.delivery_unknown_count > 0 && <StatusBlock title="有邮件投递结果未知" error>
      <p>{notification.delivery_unknown_count} 封邮件可能已被服务器接收，已占用提醒名额，不会自动重复发送。请核对收件箱和垃圾邮件。</p>
    </StatusBlock>}
    {notification.state === 'sent' && <p className="muted">服务器接收不代表邮箱最终送达或已阅读。</p>}
  </section>
}

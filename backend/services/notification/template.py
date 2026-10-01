"""固定可信站内链接和白名单字段；纯文本避免 HTML 注入。"""

from email.message import EmailMessage
from email.policy import SMTP
from zoneinfo import ZoneInfo

from services.common.sql import aware

TEMPLATE_VERSION = "low-balance-v1"


def render(job, sender, recipient, origin):
    message = EmailMessage(policy=SMTP)
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = "寝室电费低余额提醒"
    message["Message-ID"] = job["message_id"]
    captured = aware(job["captured_at"]).astimezone(ZoneInfo("Asia/Shanghai"))
    message.set_content(
        f"寝室：{job['binding_display_name']}\n"
        f"最近采集余额：{job['balance']:.2f} 元\n"
        f"提醒阈值：{job['threshold']:.2f} 元\n"
        f"采集时间：{captured:%Y-%m-%d %H:%M:%S}（Asia/Shanghai）\n\n"
        f"查看寝室电费：{origin}/monitor\n\n"
        "本邮件基于最近一次成功采集，请以学校最新余额为准。\n"
    )
    return message.as_bytes()

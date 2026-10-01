"""由专用授权进程解析五行邮件凭据，错误中不包含输入。"""

import re
from pathlib import Path

from services.notification.smtp import SmtpConfig


def read_email_auth(path: Path):
    try:
        if not path.is_absolute() or path.is_symlink() or path.stat().st_size > 8192:
            raise ValueError()
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        if len(lines) != 5:
            raise ValueError()
        sender, host, port, password, recipient = lines
        sender, host, recipient = sender.strip(), host.strip(), recipient.strip()
        if not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", recipient
        ):
            raise ValueError()
        config = SmtpConfig(
            host=host, port=int(port.strip()), sender=sender, username=sender,
            password=password, tls="implicit" if int(port.strip()) == 465 else "starttls",
        )
        del lines, password
        return config, recipient
    except Exception:
        raise RuntimeError("邮件凭据缺失或五行格式错误，未输出文件内容") from None

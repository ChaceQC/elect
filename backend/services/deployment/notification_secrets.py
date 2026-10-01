"""本域邮箱密钥和不可用的 SMTP 占位配置，不覆写既有 Secret。"""

import base64
import secrets

from .provision import write_file


def provision_notifications(directory):
    for name, value in {
        "notification_encryption_key_bundle": {
            "current": "v1",
            "keys": {"v1": base64.b64encode(secrets.token_bytes(32)).decode()},
        },
        "smtp_credentials": {
            "host": "smtp.example.invalid",
            "port": 587,
            "sender": "replace@example.invalid",
            "username": "replace@example.invalid",
            "password": "replace-with-secret",
            "tls": "starttls",
        },
    }.items():
        path = directory / name
        if path.is_symlink():
            raise ValueError("邮件 Secret 不能是符号链接")
        if not path.exists():
            write_file(directory, name, value)

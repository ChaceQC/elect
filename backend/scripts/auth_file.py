"""显式烟测的本地凭据载入；只读入内存，不输出正文。"""

import json
import re
from pathlib import Path


def read_auth(path):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig").strip()
        try:
            value = json.loads(raw)
        except ValueError:
            value = {}
            for line in raw.splitlines():
                match = re.fullmatch(
                    r"\s*(username|account|sdgl_username|账号|学号|"
                    r"password|pwd|sdgl_password|密码)\s*[:=：]\s*(.*?)\s*",
                    line,
                    re.I,
                )
                if match:
                    value[match[1].lower()] = match[2]
            if not value:
                lines = [line.strip() for line in raw.splitlines() if line.strip()]
                if len(lines) == 2:
                    value = dict(username=lines[0], password=lines[1])
        student = next(
            (
                value[key]
                for key in ["username", "account", "sdgl_username", "账号", "学号"]
                if key in value
            ),
            None,
        )
        password = next(
            (value[key] for key in ["password", "pwd", "sdgl_password", "密码"] if key in value),
            None,
        )
        if (
            not isinstance(student, str)
            or not student
            or not isinstance(password, str)
            or not password
        ):
            raise ValueError()
        return student, password
    except Exception:
        raise RuntimeError("测试凭据文件缺失或格式错误") from None

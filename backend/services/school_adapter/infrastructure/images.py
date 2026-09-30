import base64
import re

from services.common.errors import ErrorCode
from services.common.http import ApiError


def validate_image(value):
    try:
        if not isinstance(value, str) or len(value) > 350_000:
            raise ValueError()
        match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", value)
        if not match:
            raise ValueError()
        raw = base64.b64decode(match[2], validate=True)
        signature = b"\x89PNG\r\n\x1a\n" if match[1] == "png" else b"\xff\xd8\xff"
        if not raw.startswith(signature) or not 1 <= len(raw) <= 256 * 1024:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校验证码图片格式异常") from None

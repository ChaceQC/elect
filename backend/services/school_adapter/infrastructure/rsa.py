"""学校公开的小端、零填充分块协议；与存储加密独立。"""

from services.common.errors import ErrorCode
from services.common.http import ApiError

MODULUS = int(
    "00b5eeb166e069920e80bebd1fea4829d3d1f3216f2aabe79b6c47a3c18dcee5"
    "fd22c2e7ac519cab59198ece036dcf289ea8201e2a0b9ded307f8fb704136eaeb6"
    "70286f5ad44e691005ba9ea5af04ada5367cd724b5a26fdb5120cc95b6431604bd"
    "219c6b7d83a6f8f24b43918ea988a76f93c333aa5a20991493d4eb1117e7b1",
    16,
)


def encrypt_password(password: str):
    try:
        raw = password.encode("latin-1")
    except UnicodeEncodeError:
        raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "学校密码加密协议暂不支持此字符") from None
    if not 1 <= len(raw) <= 1024:
        raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "密码长度不符合要求")
    raw += b"\0" * (-len(raw) % 128)
    return "".join(
        f"{pow(int.from_bytes(raw[i : i + 128], 'little'), 65537, MODULUS):0256x}"
        for i in range(0, len(raw), 128)
    )

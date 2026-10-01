"""已验证的 ASP.NET 普通表单；支付客户端不携带 SDGL token。"""

import html
import io
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from PIL import Image, UnidentifiedImageError

from services.common.errors import ErrorCode
from services.common.http import ApiError

PAY_HOSTS = {"cwcwx.hbue.edu.cn", "sdgl.hbue.edu.cn", "pay.hbue.edu.cn"}
PATHS = {"/zhifu/payaccept.aspx", "/zhifu/paymain.aspx", "/zhifu/makeqrcode.aspx"}


def check_pay_url(url, *, accept=False):
    try:
        parsed = urlsplit(str(url))
        if (
            parsed.hostname not in PAY_HOSTS
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.path.lower() not in PATHS
            or parsed.scheme not in {"http", "https"}
            or parsed.port not in {None, 80 if parsed.scheme == "http" else 443}
            or (parsed.scheme == "http" and parsed.hostname != "cwcwx.hbue.edu.cn")
        ):
            raise ValueError()
        if accept:
            ids = parse_qs(parsed.query).get("prePayId", [])
            if parsed.path.lower() != "/zhifu/payaccept.aspx" or len(ids) != 1:
                raise ValueError()
            if not re.fullmatch(r"[a-zA-Z0-9]{1,512}", ids[0]):
                raise ValueError()
            return ids[0]
        return parsed
    except (ValueError, TypeError):
        raise ApiError(502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "学校支付地址不受支持") from None


class HiddenFields(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        value = dict(attrs)
        if tag == "input" and (value.get("type") or "").lower() == "hidden" and value.get("name"):
            self.fields[value["name"]] = value.get("value") or ""


def hidden_fields(text):
    parser = HiddenFields()
    parser.feed(text)
    if not parser.fields.get("__VIEWSTATE"):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校支付页面缺少当前表单状态")
    return parser.fields


def form_fields(hidden, step):
    if not hidden.get("__VIEWSTATE"):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校支付表单状态未取得")
    value = {
        key: item
        for key, item in hidden.items()
        if key not in {"ScriptManager1", "__ASYNCPOST", "btn_wx", "btn_wx_show"}
    }
    return {
        **value,
        "hvalue_pay": "0",
        "i_bank": "1/WX/微信支付",
        "cb": "on",
        "h_cftz": "0",
        "btn_wx" if step == "E02" else "btn_wx_show": "确认支付" if step == "E02" else "",
    }


def qr_url(text, base):
    match = re.search(r"MakeQRCode\.aspx\?data=([^\s\"'<>|]+)", html.unescape(text))
    if not match:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校支付页面没有二维码地址")
    value = urljoin(base, "MakeQRCode.aspx?data=" + match[1])
    check_pay_url(value)
    return value


def image_bytes(raw):
    try:
        if not 1 <= len(raw) <= 2 * 1024 * 1024:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as picture:
            if not all(1 <= side <= 2048 for side in picture.size):
                raise ValueError()
            mime = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(picture.format)
            picture.verify()
        with Image.open(io.BytesIO(raw)) as picture:
            picture.load()
            if mime:
                return raw, mime
            output = io.BytesIO()
            picture.convert("RGB").save(output, format="PNG")
            return output.getvalue(), "image/png"
    except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校二维码图片无法解码") from None

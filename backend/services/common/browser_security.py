"""浏览器写请求检查；调用方必须先从已验证会话取得 CSRF token。"""

from secrets import compare_digest

from .errors import ErrorCode
from .http import ApiError


def require_origin(request):
    if request.headers.get("Origin") != request.app.state.public_origin:
        raise ApiError(403, ErrorCode.ORIGIN_REJECTED, "请求来源不受信任")


def require_browser_write(request, session_csrf_token: str):
    require_origin(request)
    supplied = request.headers.get("X-CSRF-Token", "")
    if (
        not supplied
        or not session_csrf_token
        or not compare_digest(
            supplied.encode(),
            session_csrf_token.encode(),
        )
    ):
        raise ApiError(403, ErrorCode.CSRF_REJECTED, "请刷新会话后重试")

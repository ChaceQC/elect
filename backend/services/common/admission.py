"""只计算领域已在owner锁内读取的预算，不跨领域查询。"""

from services.common.errors import ErrorCode
from services.common.http import ApiError


def enforce_budget(recent, pending, *, minute=6, daily=60, maximum=8):
    retry = 0
    if recent["daily"] >= daily:
        retry = max(1, int(86400 - (recent["now"] - recent["earliest"]).total_seconds()) + 1)
    if recent["minute"] >= minute or pending >= maximum:
        retry = max(retry, 60)
    if retry:
        raise ApiError(429, ErrorCode.RATE_LIMITED, "请求额度已用完，请稍后用原请求重试",
                       True, retry_after_seconds=retry)

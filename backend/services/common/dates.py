"""上海日期范围与数据库 UTC 半开边界。"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .errors import ErrorCode
from .http import ApiError

SHANGHAI = ZoneInfo("Asia/Shanghai")


def today():
    return datetime.now(SHANGHAI).date()


def check_range(start, end):
    if not 1 <= (end - start).days + 1 <= 366 or end > today():
        raise ApiError(422, ErrorCode.INVALID_DATE_RANGE, "日期须含首尾、不超过366天且不晚于今天")


def utc_bounds(start, end):
    check_range(start, end)
    return tuple(
        datetime.combine(day, time(), SHANGHAI).astimezone(UTC).replace(tzinfo=None)
        for day in (start, end + timedelta(days=1))
    )


def windows(start: date, end: date):
    check_range(start, end)
    while start <= end:
        stop = min(start + timedelta(days=6), end)
        yield start, stop
        start = stop + timedelta(days=1)

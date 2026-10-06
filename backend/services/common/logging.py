"""结构化日志只接受白名单字段，不记录请求体、SQL 或原始异常。"""

import json
import logging
from datetime import UTC, datetime

FIELDS = {"service", "domain", "route", "request_id", "event", "error_code", "status",
          "duration_ms", "count", "exception_type", "database_error", "role"}
logger = logging.getLogger("elect")


class SafeFormatter(logging.Formatter):
    def format(self, record):
        payload = {"time": datetime.now(UTC).isoformat(), "level": record.levelname}
        payload.update({key: record.__dict__[key] for key in FIELDS if key in record.__dict__})
        return json.dumps(payload, ensure_ascii=False)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for name in ("sqlalchemy.engine", "asyncmy", "aio_pika", "aiormq", "httpx"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def log(event: str, **fields):
    logger.info("", extra={"event": event, **{k: v for k, v in fields.items() if k in FIELDS}})


def log_failure(event, error, **fields):
    """异常只取代码定义的类别和整数数据库编号，不格式化原文或参数。"""
    original = getattr(error, "orig", None)
    args = getattr(original, "args", ())
    number = args[0] if args and type(args[0]) is int else None
    log(event, **fields, exception_type=type(error).__name__, database_error=number,
        error_code=f"MYSQL_{number}" if number is not None else type(error).__name__)

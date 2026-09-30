"""结构化日志只接受白名单字段，不记录请求体、SQL 或原始异常。"""

import json
import logging
from datetime import UTC, datetime

FIELDS = {"service", "request_id", "event", "error_code", "status", "duration_ms", "count"}
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

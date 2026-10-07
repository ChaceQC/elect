"""仅隔离验收推进手动受理分钟窗口；保留每日计数、原键和运行事实。"""

import os

from services.common.sql import execute


async def next_request_minute(engine, owner):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("只允许合成验收推进请求窗口")
    async with engine.begin() as conn:
        await execute(conn, "UPDATE monitor_run_requests SET "
                      "created_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 61 SECOND) "
                      "WHERE owner_user_id=:id", id=owner.bytes)

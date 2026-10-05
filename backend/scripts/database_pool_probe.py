"""真实MySQL上的有限池等待/超时/归还；仅显式一次性环境运行。"""

import asyncio
import json
import os
import time

from sqlalchemy.exc import TimeoutError as PoolTimeout

from services.common.database import create_database, database_ready, migration_head, pool_options
from services.common.runtime import Runtime, read_secret
from services.common.sql import first


async def probe():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于隔离测试项目")
    options = pool_options()
    capacity = options["pool_size"] + options["max_overflow"]
    runtime = Runtime.model_validate_json(read_secret("/run/secrets/monitoring_runtime.json"))
    engine = create_database(runtime.db_url.get_secret_value())
    held = []
    try:
        held = [await engine.connect() for _ in range(capacity)]
        started = time.perf_counter()
        waiting = asyncio.create_task(engine.connect().__aenter__())
        await asyncio.sleep(0.2)
        assert not waiting.done()
        await held.pop().close()
        held.append(await waiting)
        wait = time.perf_counter() - started
        started = time.perf_counter()
        try:
            async with engine.connect():
                raise AssertionError("已超过连接池上限")
        except PoolTimeout:
            timeout = time.perf_counter() - started
        assert timeout >= 2.9
        for conn in held:
            await conn.close()
        held.clear()
        await database_ready(engine, migration_head("monitoring"))
        async with engine.connect() as conn:
            utc = await first(conn, "SELECT @@session.time_zone AS zone")
            assert utc["zone"] == "+00:00"
        assert engine.pool.checkedout() == 0
        return {"capacity": capacity, "wait_seconds": round(wait, 4),
                "timeout_seconds": round(timeout, 4), "checkedout_after": 0,
                "recovered_ready": True, "utc": True}
    finally:
        for conn in held:
            await conn.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(probe())))
    except Exception:
        raise SystemExit("数据库池验收失败；未输出连接凭据") from None

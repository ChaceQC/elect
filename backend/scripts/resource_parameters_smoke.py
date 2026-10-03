"""第三步实际基础服务验证；仅合成事件和健康请求，不调用学校/SMTP。"""

import argparse
import asyncio
import os
import ssl
import time
from uuid import UUID

import httpx

from scripts.combined_status import ROLES
from scripts.deployment_smoke import fixture_event, verify_live_duplicate_event
from services.common.database import create_database
from services.common.outbox import append_event
from services.common.runtime import Runtime, read_secret
from services.common.sql import first

EXPECTED = {
    "max_connections": 40, "innodb_buffer_pool_size": 128 * 1024**2,
    "table_open_cache": 256, "table_definition_cache": 400,
    "temptable_max_ram": 32 * 1024**2, "tmp_table_size": 8 * 1024**2,
    "max_heap_table_size": 8 * 1024**2, "innodb_flush_log_at_trx_commit": 1,
    "sync_binlog": 1, "log_bin": 1,
}


async def ready(runtimes, engines):
    async with engines["identity"].connect() as conn:
        values = dict(await first(conn, "SELECT " + ",".join(
            f"@@{key} AS {key}" for key in EXPECTED
        )))
    assert values == EXPECTED
    context = ssl.create_default_context(cafile=os.environ["ELECT_INTERNAL_CA_FILE"])
    async with httpx.AsyncClient(verify=context, trust_env=False, timeout=5) as client:
        started = time.perf_counter()
        urls = [f"{'https' if host in {'identity', 'school-adapter'} else 'http'}://"
                f"{host}:8000/health/ready" for host in ROLES]
        responses = await asyncio.gather(*(client.get(url) for url in urls for _ in range(4)))
        assert all(r.status_code == 200 and r.json()["status"] == "ready" for r in responses)
    print({"mysql_effective": values, "concurrent_health_reads": 32,
           "health_batch_seconds": round(time.perf_counter() - started, 4)})
    await verify_live_duplicate_event(runtimes, engines)


async def pressure(mode, engines):
    identifier = UUID(os.environ["ELECT_RESOURCE_EVENT_ID"])
    if mode == "enqueue":
        event = fixture_event().model_copy(update={
            "event_id": identifier, "dedupe_key": str(identifier),
        })
        async with engines["identity"].begin() as conn:
            await append_event(conn, event)
        return
    async with asyncio.timeout(45):
        while True:
            async with engines["identity"].connect() as conn:
                row = await first(conn, "SELECT published_at,publish_attempts FROM outbox_events "
                                  "WHERE event_id=:id", id=identifier.bytes)
            async with engines["audit"].connect() as conn:
                count = await first(
                    conn, "SELECT COUNT(*) AS n FROM audit_events WHERE event_id=:id",
                    id=identifier.bytes,
                )
                inbox = await first(
                    conn, "SELECT COUNT(*) AS n FROM inbox_events WHERE event_id=:id",
                    id=identifier.bytes,
                )
            assert row is not None
            if mode == "blocked":
                assert row["published_at"] is None and count["n"] == inbox["n"] == 0
                if row["publish_attempts"] == 0:
                    await asyncio.sleep(0.5)
                    continue
                print("实际MQ内存告警期间Outbox保留未发布：通过")
                return
            if row["published_at"] is not None and count["n"] == inbox["n"] == 1:
                print("解除流控后confirm/签名/提交后ACK，Outbox与Audit/Inbox唯一完成：通过")
                return
            await asyncio.sleep(0.5)


async def main(mode):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于隔离测试项目")
    runtimes = {name: Runtime.model_validate_json(read_secret(f"/run/secrets/{name}_runtime.json"))
                for name in ["identity", "audit"]}
    engines = {name: create_database(runtime.db_url.get_secret_value())
               for name, runtime in runtimes.items()}
    try:
        if mode == "ready":
            await ready(runtimes, engines)
        else:
            await pressure(mode, engines)
    finally:
        for engine in engines.values():
            await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["ready", "enqueue", "blocked", "delivered"])
    try:
        asyncio.run(main(parser.parse_args().mode))
    except Exception:
        raise SystemExit("资源参数验收失败；未输出凭据/消息载荷") from None

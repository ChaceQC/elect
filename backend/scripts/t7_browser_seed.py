"""合成学校创建正式应用会话；仅把Cookie写入受限本地文件供容器浏览器读取。"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from scripts.room_test_setup import ready_default
from scripts.t2_smoke import browser, fixture_apps, login, prepare
from services.common.ids import new_id
from services.common.sql import first
from services.room.worker import sync_tick


async def seed(path):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅允许合成隔离会话")
    apps, _ = await fixture_apps()
    try:
        async with browser(apps["gateway"]) as client:
            user = await login(
                client, await prepare(client, "synthetic-t7-browser-" + str(new_id()))
            )
            accepted = await client.post(
                "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
            )
            assert accepted.status_code == 202
            assert await sync_tick(apps["room"])
            await ready_default(client, apps["room"])
            async with apps["room"].state.database.connect() as conn:
                foreign = await first(
                    conn, "SELECT id FROM room_bindings WHERE owner_user_id<>:owner LIMIT 1",
                    owner=UUID(user["id"]).bytes,
                )
            assert foreign, "需要第二个合成用户的绑定用于对象归属验收"
            document = {"cookie": client.cookies.get("__Host-elect_session"),
                        "foreign_binding": str(UUID(bytes=foreign["id"]))}
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(document, output)
            if os.environ.get("ELECT_RESULT_UID"):
                os.chown(path, int(os.environ["ELECT_RESULT_UID"]),
                         int(os.environ["ELECT_RESULT_GID"]))
        print("正式应用会话已由合成学校创建并受限保存；未输出Cookie或身份数据")
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(seed(parser.parse_args().output))

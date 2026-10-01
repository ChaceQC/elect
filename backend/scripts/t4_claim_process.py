"""显式一次性验收子进程：提交领取后等待SIGKILL，不访问学校。"""

import argparse
import asyncio
import os
from uuid import UUID

from services.common.database import create_database
from services.common.runtime import Runtime, read_secret
from services.monitoring.execution import claim_run


async def run(run_id):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于一次性测试")
    runtime = Runtime.model_validate_json(read_secret("/run/secrets/monitoring_runtime.json"))
    engine = create_database(runtime.db_url.get_secret_value())
    try:
        execution = await claim_run(engine, run_id)
        if not execution:
            raise RuntimeError("无可领取运行")
        print("claimed", flush=True)
        await asyncio.Event().wait()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=UUID, required=True)
    try:
        asyncio.run(run(parser.parse_args().run_id))
    except Exception:
        raise SystemExit("测试领取失败，未输出运行Secret") from None

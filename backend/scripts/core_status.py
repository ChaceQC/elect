"""七容器实际HTTP/TLS、领域心跳与恢复禁用检查，不调用学校。"""

import argparse
import asyncio
import os
import ssl

import httpx

from scripts.combined_status import ROLES
from services.common.domains import CORE_DOMAINS
from services.common.ids import new_id
from services.common.runtime import Runtime, read_secret
from services.common.service_client import ServiceClient


async def verify(mode):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于隔离项目")
    context = ssl.create_default_context(cafile=os.environ["ELECT_INTERNAL_CA_FILE"])
    async with httpx.AsyncClient(verify=context, trust_env=False, timeout=6) as client:
        async with asyncio.timeout(45):
            while True:
                try:
                    response = await client.get("https://identity:8000/health/ready")
                    assert response.status_code == 200
                    value = response.json()
                    assert set(value["domains"]) == set(CORE_DOMAINS)
                    for name, state in value["domains"].items():
                        expected = set() if mode == "restored" else ROLES[name]
                        assert set(state["background_roles"]) == expected
                        assert state["status"] == ("degraded" if mode == "mq-down" else "ready")
                    break
                except (AssertionError, httpx.HTTPError):
                    await asyncio.sleep(0.5)
    runtime = Runtime.model_validate_json(read_secret("/run/secrets/gateway_runtime.json"))
    caller = ServiceClient(runtime)
    try:
        result = await caller.call("identity", "/browser/agreement", "identity:browser", new_id())
        assert result["version"]
    finally:
        await caller.close()
    print(f"核心TLS/受认证领域调用/心跳：{mode}通过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["ready", "mq-down", "restored"])
    asyncio.run(verify(parser.parse_args().mode))

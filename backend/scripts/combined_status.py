"""实际容器API/角色健康验收；只读取健康状态，不调用学校或业务写入口。"""

import argparse
import asyncio
import os
import ssl
import time

import httpx

ROLES = {
    "identity": {"relay", "recovery"},
    "school-adapter": {"relay", "cleanup"},
    "room": {"relay", "worker"},
    "monitoring": {"relay", "scheduler", "worker", "recovery", "alerts"},
    "notification": {"relay", "recovery"},
    "payment": {"relay", "worker", "recovery"},
    "audit": {"audit"},
    "gateway": set(),
}


async def verify(mode):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于隔离测试项目")
    started = time.time()
    context = ssl.create_default_context(cafile=os.environ["ELECT_INTERNAL_CA_FILE"])
    async with httpx.AsyncClient(verify=context, trust_env=False, timeout=5) as client:
        async with asyncio.timeout(40):
            while True:
                values = {}
                try:
                    for host, expected in ROLES.items():
                        scheme = "https" if host in {"identity", "school-adapter"} else "http"
                        response = await client.get(f"{scheme}://{host}:8000/health/ready")
                        assert response.status_code == 200
                        value = response.json()
                        roles = value["background_roles"]
                        if mode == "restored":
                            assert roles == {}
                        else:
                            assert set(roles) == expected
                            if mode == "ready":
                                assert value["status"] == "ready"
                            elif expected:
                                assert value["status"] == "degraded"
                                for role, state in roles.items():
                                    if role not in {"relay", "audit"}:
                                        assert state["last_success"] > started
                        values[host] = {"status": value["status"], "roles": sorted(roles)}
                    print(values)
                    break
                except (AssertionError, httpx.HTTPError):
                    await asyncio.sleep(0.5)
    print(f"实际容器七域/API角色检查 {mode}：通过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["ready", "mq-down", "restored"])
    asyncio.run(verify(parser.parse_args().mode))

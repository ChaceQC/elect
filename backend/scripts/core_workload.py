"""复用学校/支付/邮件故障夹具，核心领域之间走真实进程内分派。"""

import asyncio
import os

from scripts.domain_combined_smoke import setup, verify
from scripts.t5_fixtures import close_apps
from services.common.domains import CORE_DOMAINS
from services.common.sql import execute
from services.core.dispatch import Dispatcher


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于隔离项目")
    os.environ["ELECT_PROCESS_MODE"] = "combined"
    apps, school = await setup()
    dispatcher = Dispatcher({name: apps[name] for name in CORE_DOMAINS})
    for app in apps.values():
        app.state.service_client.local = dispatcher
    try:
        await verify(apps, school)
        print("核心直接调用：同步/默认Saga/采集/支付unknown/邮件unknown/后台退出通过")
    finally:
        supervisors = [app.state.background for app in apps.values()
                       if getattr(app.state, "background", None)]
        for supervisor in supervisors:
            supervisor.request_stop()
        await asyncio.gather(*(supervisor.close() for supervisor in supervisors))
        async with apps["payment"].state.database.begin() as conn:
            for owner in getattr(apps["payment"].state, "test_owners", []):
                await execute(conn, "UPDATE payment_operations SET state='cancelled',"
                              "lease_owner=NULL,lease_until=NULL WHERE owner_user_id=:owner",
                              owner=owner.bytes)
                await execute(conn, "UPDATE payment_orders SET next_check_at=NULL "
                              "WHERE owner_user_id=:owner", owner=owner.bytes)
        await close_apps(apps)


if __name__ == "__main__":
    asyncio.run(main())

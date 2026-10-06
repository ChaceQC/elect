"""隔离恢复验收：快照后合成建单/SMTP接受，恢复旧快照不得再外发。"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx

from scripts.domain_combined_smoke import setup
from scripts.t4_monitor_smoke import enable
from scripts.t5_alert_smoke import collect
from scripts.t5_fixtures import SmtpSimulator, event_for_sample, make_job
from scripts.t6_fixtures import PaymentSchool
from scripts.t6_smoke import account
from services.common.config_contract import SideEffectPolicy
from services.common.ids import new_id
from services.common.internal_dto import DispatchOrder
from services.common.security import Principal
from services.common.sql import execute, first
from services.monitoring.scheduler import scheduler_tick
from services.notification.consumer import consume_alert
from services.notification.worker import worker_tick as mail_tick
from services.payment.api import CreateCommand
from services.payment.jobs import claim
from services.payment.orders import create_order
from services.payment.worker import worker_tick as payment_tick
from services.room.repository import RoomRepository
from services.school_adapter.infrastructure.payment_ledger import PaymentLedger
from services.school_adapter.infrastructure.payment_transport import PaymentTransport


async def prepared_order(apps, owner):
    rooms = await RoomRepository(apps["room"].state.database).list(owner, "", 1, 100)
    binding = next(item for item in rooms.items if item.id == rooms.default_binding_id)
    credential = await apps["school_adapter"].state.school_credentials.current(owner)
    principal = Principal("payment", owner, 1, new_id())
    accepted = await create_order(
        apps["payment"].state.database, principal,
        CreateCommand(binding_id=binding.id, amount="1.00", idempotency_key=str(new_id())),
        binding.model_dump(mode="json"),
        {"credential_ref": str(UUID(bytes=credential["id"])),
         "credential_version": credential["version"]},
    )
    row = await claim(apps["payment"].state.database, accepted.order_id)
    command = DispatchOrder(
        owner_user_id=owner, request_id=new_id(), order_id=accepted.order_id,
        operation_id=UUID(bytes=row["operation_id"]), lease_owner=row["lease_owner"],
        upstream_operation_id=UUID(bytes=row["upstream_operation_id"]),
        credential_ref=UUID(bytes=row["credential_ref"]),
        credential_version=row["credential_version"], binding_id=binding.id,
        amount="1.00", currency="CNY",
    )
    target = await apps["payment"].state.service_client.call(
        "room", "/controls/query-target", "room:query", principal.request_id,
        {"binding_id": str(binding.id)}, principal=principal,
    )
    await PaymentLedger(apps["school_adapter"].state).prepare(command, {
        "school_room_id": target["school_room_id"], "amount": "1.00",
        "pay_url": None, "prepay_id": None, "sdgl_order_id": None,
    })
    return str(accepted.order_id)


async def seed(apps, school):
    client, user, _ = await account(apps, school)
    try:
        await enable(client)
    finally:
        await client.aclose()
    owner = UUID(user["id"])
    sample = await collect(apps["monitoring"].state.database, owner, "19.99")
    job, _ = await make_job(apps, sample)
    return {"owner": str(owner), "sample": str(sample),
            "job": str(UUID(bytes=job["id"])), "order": await prepared_order(apps, owner),
            "last_commit_at": datetime.now(UTC).isoformat()}


async def after_backup(apps, state):
    owner, order = UUID(state["owner"]), UUID(state["order"])
    adapter, school = apps["school_adapter"].state, PaymentSchool()
    credential = await adapter.school_credentials.current(owner)
    payload = adapter.school_credentials.payload(credential)
    cached = await adapter.school_store.get_secret(
        f"school_adapter:token:{UUID(bytes=credential['id'])}:{credential['version']}"
    )
    school.tokens[cached["token"]] = payload["student_id"]
    adapter.school_protocol.transport.transport = httpx.MockTransport(school.handler)
    adapter.payment_transport = PaymentTransport(
        adapter.school_store, transport=httpx.MockTransport(school.handler), resolve=False
    )
    adapter.side_effect_policy = SideEffectPolicy(
        payment_order_writes=True, payment_form_writes=True
    )
    async with apps["payment"].state.database.begin() as conn:
        await execute(
            conn, "UPDATE payment_operations SET lease_until=UTC_TIMESTAMP(6),"
            "next_attempt_at=UTC_TIMESTAMP(6) WHERE order_id=:id", id=order.bytes,
        )
    assert await payment_tick(apps["payment"], order_id=order)
    assert school.payment_posts["D01"] == 1
    async with SmtpSimulator() as smtp:
        apps["notification"].state.smtp = smtp.transport
        assert await mail_tick(apps["notification"], UUID(state["job"]))
        assert len(smtp.messages) == 1
    print("快照之后：模拟学校D01一次、SMTP模拟器接受一封；未执行真实副作用")
    state["post_backup_commit_at"] = datetime.now(UTC).isoformat()


async def restored(apps, state):
    async with apps["notification"].state.database.connect() as conn:
        job = await first(conn, "SELECT state FROM notification_jobs WHERE id=:id",
                          id=UUID(state["job"]).bytes)
    async with apps["payment"].state.database.connect() as conn:
        order = await first(conn, "SELECT state FROM payment_orders WHERE id=:id",
                            id=UUID(state["order"]).bytes)
    adapter = apps["school_adapter"].state
    row = await PaymentLedger(adapter).get(UUID(state["owner"]), UUID(state["order"]))
    assert job["state"] == "delivery_unknown" and order["state"] == "submit_unknown"
    assert row["state"] == "unknown" and not row["dispatched_at"]
    assert adapter.school_credentials.payload(
        await adapter.school_credentials.current(UUID(state["owner"]))
    )["student_id"].startswith("synthetic-")
    assert not await payment_tick(apps["payment"], order_id=UUID(state["order"]))
    event = await event_for_sample(apps["monitoring"], UUID(state["sample"]))
    assert not await consume_alert(apps["notification"], event)
    async with SmtpSimulator() as smtp:
        apps["notification"].state.smtp = smtp.transport
        assert not await mail_tick(apps["notification"], UUID(state["job"]))
        assert smtp.connections == 0
    async with apps["notification"].state.database.connect() as conn:
        jobs = await first(conn, "SELECT COUNT(*) AS n FROM notification_jobs "
                           "WHERE alert_slot_id=:id", id=event.payload.alert_slot_id.bytes)
        assert jobs["n"] == 1
    assert await scheduler_tick(apps["monitoring"].state.database) == 0
    async with apps["monitoring"].state.database.connect() as conn:
        sample = await first(conn, "SELECT balance FROM monitor_samples WHERE id=:id",
                             id=UUID(state["sample"]).bytes)
    assert format(sample["balance"], ".2f") == "19.99"
    print("恢复快照：样本/密文保留、建单/邮件未知占位、无重发或新采集；人工对账前保持隔离")


async def main(args):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅允许显式隔离测试")
    apps, school = await setup()
    try:
        if args.mode == "seed":
            state = await seed(apps, school)
            from scripts.r7_recovery_data import seed as seed_r7

            state["r7"] = await seed_r7(apps, state)
            args.state_file.write_text(json.dumps(state))
            args.state_file.chmod(0o600)
            if os.environ.get("ELECT_RESULT_UID"):
                os.chown(args.state_file, int(os.environ["ELECT_RESULT_UID"]),
                         int(os.environ["ELECT_RESULT_GID"]))
        else:
            state = json.loads(args.state_file.read_text())
            if args.mode == "after-backup":
                await after_backup(apps, state)
                args.state_file.write_text(json.dumps(state))
            else:
                await restored(apps, state)
                from scripts.r7_recovery_data import verify as verify_r7

                await verify_r7(apps, state)
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["seed", "after-backup", "restored"])
    parser.add_argument("--state-file", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))

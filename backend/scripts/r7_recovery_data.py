"""仅在T7隔离项目加入R7观测、真实修复别名和冷热去重恢复证据。"""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

from services.common.archive_verify import verify_archives, verify_cold_links
from services.common.ids import new_id
from services.common.outbox import consume_once
from services.common.sql import execute, first
from services.deployment.recovery_observations import verify_observations
from services.deployment.retention import batch
from services.room.balance import accept_refresh
from services.room.balance_observations import apply_observation
from services.room.history_jobs import accept_history, claim_history
from services.room.history_store import finish_history
from services.room.repair_history import repair_batch
from services.room.repository import RoomRepository
from services.school_adapter.infrastructure.balance_observations import observe

CUTOFF = datetime(2026, 1, 1)


async def repaired_alias(room, owner, binding):
    command = SimpleNamespace(start_date=date(2026, 9, 1), end_date=date(2026, 9, 14))
    root = await accept_history(room, owner, binding, command, str(new_id()), new_id())
    alias = await accept_history(room, owner, binding, command, str(new_id()), new_id())
    for _ in range(200):
        if (await RoomRepository(room).operation(owner, root))["state"] == "succeeded":
            break
        row = await claim_history(room)
        assert row and await finish_history(room, row, {"items": []}, None)
    assert (await RoomRepository(room).operation(owner, alias))["state"] == "succeeded"
    async with room.begin() as conn:
        # 仅构造旧缺陷遗留别名；根请求/窗口已真正经过完成入口。
        await execute(conn, "UPDATE room_operations SET state='running',saga_step='read_school' "
                      "WHERE id=:id", id=alias.bytes)
    assert (await repair_batch(room))["summary"]["repairable"] >= 1
    assert (await repair_batch(room, apply=True))["summary"]["applied"] >= 1
    return str(alias)


async def seed(apps, state):
    owner = UUID(state["owner"])
    room, adapter = apps["room"].state.database, apps["school_adapter"].state.database
    rooms = await RoomRepository(room).list(owner, "", 1, 100)
    binding = rooms.default_binding_id
    observed = await observe(adapter, owner, new_id(), {"data": []}, None, datetime.now(UTC))
    async with room.begin() as conn:
        await apply_observation(conn, binding.bytes, "19.99", observed["observation"])
    alias = await repaired_alias(room, owner, binding)
    key = "r7-restore-cold-" + str(new_id())
    operation = await accept_refresh(room, owner, binding, key)
    async with room.begin() as conn:
        await execute(conn, "UPDATE room_operations SET state='succeeded',saga_step='complete',"
            "next_reconcile_at=NULL,created_at='2000-01-01',updated_at='2000-01-01' WHERE id=:id",
            id=operation.bytes)
    await batch(room, "room", "room_operations", CUTOFF, apply=True)
    event = new_id()
    for name, app in apps.items():
        if not app.state.database:
            continue
        async def effect(conn, _):
            pass  # 独立副作用计数由T7 D01/SMTP模拟器验证。
        assert await consume_once(app.state.database, "r7.restore", SimpleNamespace(event_id=event),
                                  effect)
        async with app.state.database.begin() as conn:
            await execute(conn, "UPDATE inbox_events SET created_at='2000-01-01',"
                "updated_at='2000-01-01',processed_at='2000-01-01' "
                "WHERE consumer_name='r7.restore' AND event_id=:id", id=event.bytes)
        await batch(app.state.database, name, "inbox_events", CUTOFF, apply=True)
    return {"binding": str(binding), "alias": alias, "cold_key": key,
            "cold_operation": str(operation), "event": str(event),
            "sequence": observed["observation"]["sequence"]}


async def verify(apps, state):
    data, owner = state["r7"], UUID(state["owner"])
    room, adapter = apps["room"].state.database, apps["school_adapter"].state.database
    assert await verify_observations(room, adapter) >= 1
    async with room.connect() as conn:
        row = await first(conn, "SELECT observation_sequence,last_success_sequence "
                          "FROM room_balance_cache WHERE binding_id=:id",
                          id=UUID(data["binding"]).bytes)
        assert row["observation_sequence"] == row["last_success_sequence"] == data["sequence"]
    alias = await RoomRepository(room).operation(owner, UUID(data["alias"]))
    assert alias["state"] == "succeeded"
    assert str(await accept_refresh(room, owner, UUID(data["binding"]), data["cold_key"])) == (
        data["cold_operation"])
    for app in apps.values():
        if not app.state.database:
            continue
        async with app.state.database.connect() as conn:
            assert await verify_archives(conn) >= 1
            await verify_cold_links(conn)
        async def forbidden(conn, _):
            raise AssertionError("恢复后旧消息触发了处理器")
        assert not await consume_once(app.state.database, "r7.restore",
                                      SimpleNamespace(event_id=UUID(data["event"])), forbidden)
    print("R7恢复：观测计数/缓存高水位、修复别名、冷键重放及七域冷Inbox/归档保留")

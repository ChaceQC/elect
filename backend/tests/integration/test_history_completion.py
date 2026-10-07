"""R1真实MySQL：窗口完成传播、异常归属和存量修复的真实事务。"""

import pytest
from query_resource_support import requires_mysql, run, seed_binding
from test_history_admission import accept, request

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.room import history_admission as limits
from services.room.history_jobs import claim_history
from services.room.history_store import finish_history, finish_sync
from services.room.repair_history import repair_batch

pytestmark = requires_mysql


async def operation(engine, identifier):
    async with engine.connect() as conn:
        return await first(conn, "SELECT * FROM room_operations WHERE id=:id", id=identifier.bytes)


async def finish(engine, *, fail=False):
    row = await claim_history(engine)
    assert row
    assert await finish_history(engine, row, {"items": [], "request_room_id": "synthetic"},
                                "SCHOOL_TIMEOUT" if fail else None)
    return row


@pytest.mark.parametrize("size", [14, 21])
@pytest.mark.parametrize("fail", [False, True])
def test_all_windows_propagate_and_release_eight_pending(monkeypatch, size, fail):
    monkeypatch.setattr(limits, "OPERATIONS_PER_MINUTE", 24)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        root = await accept(engine, owner, binding, request(1, size))
        aliases = [await accept(engine, owner, binding) for _ in range(5)]
        row = await finish(engine, fail=fail)
        assert (await operation(engine, aliases[0]))["state"] == "running"
        aliases += [await accept(engine, owner, binding) for _ in range(2)]
        with pytest.raises(ApiError) as full:
            await accept(engine, owner, binding)
        assert full.value.status == 429
        for _ in range(size // 7 - 1):
            row = await finish(engine)
        expected = "failed" if fail else "succeeded"
        for identifier in [root, *aliases]:
            value = await operation(engine, identifier)
            assert value["state"] == expected and value["saga_step"] == "complete"
            assert value["error_code"] == ("SCHOOL_TIMEOUT" if fail else None)
        async with engine.begin() as conn:
            await finish_sync(conn, row)
        assert await accept(engine, owner, binding)
    run("room", case)


def test_wrong_owner_binding_type_and_root_are_never_propagated():
    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        root = await accept(engine, owner, binding, request(1, 14))
        aliases = [await accept(engine, owner, binding) for _ in range(3)]
        async with engine.begin() as conn:
            await execute(conn, "UPDATE room_operations SET owner_user_id=:other WHERE id=:id",
                          other=new_id().bytes, id=aliases[0].bytes)
            await execute(conn, "UPDATE room_operations SET target_binding_id=NULL WHERE id=:id",
                          id=aliases[1].bytes)
            await execute(conn, "UPDATE room_operations SET type='balance_refresh' WHERE id=:id",
                          id=aliases[2].bytes)
        await finish(engine)
        row = await finish(engine)
        for alias in aliases:
            assert (await operation(engine, alias))["state"] == "accepted"
        async with engine.begin() as conn:
            await execute(conn, "UPDATE room_operations SET state='running',"
                          "upstream_operation_id=id WHERE id=:id", id=root.bytes)
            await finish_sync(conn, row)
        assert (await operation(engine, root))["state"] == "running"
    run("room", case)


@pytest.mark.parametrize("fail", [False, True])
def test_repair_dry_run_apply_resume_and_repeat_preserve_identity(fail, monkeypatch, capsys):
    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        await accept(engine, owner, binding, request(1, 14))
        aliases = [await accept(engine, owner, binding) for _ in range(2)]
        assert (await repair_batch(engine))["counts"] == {"candidates": 2, "waiting": 2}
        await finish(engine, fail=fail)
        await finish(engine)
        # 仅构造旧缺陷遗留别名；主任务真正经过finish_history/finish_sync。
        async with engine.begin() as conn:
            for alias in aliases:
                await execute(conn, "UPDATE room_operations SET state='running',"
                              "saga_step='read_school',error_code=NULL WHERE id=:id",
                              id=alias.bytes)
        before = await operation(engine, aliases[0])
        dry = await repair_batch(engine)
        assert dry["counts"] == {"candidates": 2, "repairable": 2}
        assert (await operation(engine, aliases[0]))["state"] == "running"
        # 实际命令执行体以生产engine读取相同隔离库，默认dry-run仍不写入。
        import json
        from types import SimpleNamespace

        from pydantic import SecretStr

        from services.room import repair_history

        monkeypatch.setattr(repair_history, "load_runtime", lambda _: SimpleNamespace(
            db_url=SecretStr(engine.url.render_as_string(hide_password=False))))
        await repair_history.run(SimpleNamespace(after="00000000-0000-0000-0000-000000000000",
                                                apply=False, batch_size=100, batches=1))
        output = json.loads(capsys.readouterr().out)
        assert output["mode"] == "dry-run" and output["summary"]["repairable"] == 2
        assert (await operation(engine, aliases[0]))["state"] == "running"
        first_batch = await repair_batch(engine, apply=True, batch_size=1)
        second = await repair_batch(engine, apply=True, after=bytes.fromhex(first_batch["after"]))
        assert first_batch["counts"]["applied"] == second["counts"]["applied"] == 1
        assert not (await repair_batch(engine, apply=True))["counts"]
        after = await operation(engine, aliases[0])
        assert after["state"] == ("failed" if fail else "succeeded")
        for key in ("id", "request_digest", "idempotency_key_hash", "created_at"):
            assert before[key] == after[key]
    run("room", case)


@pytest.mark.parametrize("damage,category", [
    ("orphan", "orphan_or_chain"), ("cycle", "orphan_or_chain"),
    ("owner", "relation_conflict"), ("root_cycle", "relation_conflict"),
    ("missing_window", "window_conflict"), ("terminal", "terminal_conflict"),
])
def test_repair_leaves_unprovable_relations_untouched(damage, category):
    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        root = await accept(engine, owner, binding, request(1, 14))
        alias = await accept(engine, owner, binding)
        await finish(engine)
        await finish(engine)
        async with engine.begin() as conn:
            await execute(conn, "UPDATE room_operations SET state='running' WHERE id=:id",
                          id=alias.bytes)
            if damage in {"orphan", "cycle"}:
                await execute(conn, "UPDATE room_operations SET upstream_operation_id=:up "
                              "WHERE id=:id", id=alias.bytes,
                              up=new_id().bytes if damage == "orphan" else alias.bytes)
            elif damage == "owner":
                await execute(conn, "UPDATE room_operations SET owner_user_id=:owner WHERE id=:id",
                              id=alias.bytes, owner=new_id().bytes)
            elif damage == "root_cycle":
                await execute(conn, "UPDATE room_operations SET upstream_operation_id=:alias "
                              "WHERE id=:id", alias=alias.bytes, id=root.bytes)
            elif damage == "missing_window":
                await execute(conn, "DELETE FROM history_sync_windows ORDER BY start_date LIMIT 1")
            else:
                await execute(conn, "UPDATE room_operations SET state='failed' WHERE id=:id",
                              id=root.bytes)
        report = await repair_batch(engine, apply=True)
        assert report["counts"] == {"candidates": 1, category: 1}
        assert (await operation(engine, alias))["state"] == "running"
    run("room", case)

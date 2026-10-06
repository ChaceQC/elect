"""一次性MySQL的R3恢复夹具；实际领域迁移/租约/发送栅栏，外部副作用仅计数。"""

import asyncio
import re
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from alembic import command

from scripts.migrations import configuration
from services.common.database import create_database
from services.common.internal_dto import DispatchOrder, SendPermit
from services.common.sql import execute, first
from services.notification import recovery, repository
from services.notification.worker import worker_tick
from services.room.history_jobs import accept_history, claim_history
from services.room.history_store import finish_history
from services.school_adapter.infrastructure.payment_ledger import PaymentLedger

DOMAINS = ("room", "school_adapter", "notification")
OWNER, BINDING, CREDENTIAL, ORDER, UPSTREAM, OPERATION, JOB = [UUID(int=i) for i in range(101, 108)]


class RecoveryState:
    def __init__(self, prefix):
        if not re.fullmatch(r"elect_r3_[a-z0-9_]{1,24}", prefix):
            raise ValueError("仅允许一次性R3数据库前缀")
        self.prefix = prefix
        self.engines = {name: create_database(
            f"mysql+asyncmy://root@query-mysql/{prefix}_{name}",
        ) for name in DOMAINS}
        assert all(engine.pool.size() == 2 and engine.pool._max_overflow == 1
                   for engine in self.engines.values())

    async def close(self):
        await asyncio.gather(*(engine.dispose() for engine in self.engines.values()))

    async def prepare(self):
        root = create_database("mysql+asyncmy://root@query-mysql/mysql")
        try:
            async with root.begin() as conn:
                assert (await first(conn, "SELECT VERSION() AS v"))["v"].startswith("8.4.")
                for domain in DOMAINS:
                    await execute(conn, f"CREATE DATABASE `{self.prefix}_{domain}`")
            for domain, engine in self.engines.items():
                async with engine.begin() as conn:
                    def migrate(sync_conn, domain=domain):
                        config = configuration(domain)
                        config.attributes["connection"] = sync_conn
                        command.upgrade(config, "head")
                    await conn.run_sync(migrate)
                    await execute(conn, "CREATE TABLE r3_effects (kind VARCHAR(32) PRIMARY KEY,"
                                  "n INT NOT NULL) ENGINE=InnoDB")
        finally:
            await root.dispose()

    def payment(self):
        command = DispatchOrder(owner_user_id=OWNER, request_id=UUID(int=110), order_id=ORDER,
                                operation_id=OPERATION, lease_owner="synthetic-lease",
                                upstream_operation_id=UPSTREAM, credential_ref=CREDENTIAL,
                                credential_version=1, binding_id=BINDING, amount="1.00",
                                currency="CNY")
        state = SimpleNamespace(
            database=self.engines["school_adapter"],
            school_credentials=SimpleNamespace(
                crypto=SimpleNamespace(seal=lambda *_: b"synthetic")),
            service_client=SimpleNamespace(call=AsyncMock(return_value={
                "can_dispatch": True, "upstream_operation_id": str(UPSTREAM),
            })),
        )
        return PaymentLedger(state), command

    async def effect(self, domain, kind):
        async with self.engines[domain].begin() as conn:
            await execute(conn, "INSERT INTO r3_effects VALUES (:kind,1) "
                          "ON DUPLICATE KEY UPDATE n=n+1", kind=kind)

    async def before(self):
        room, school, notification = (self.engines[name] for name in DOMAINS)
        async with room.begin() as conn:
            await execute(conn, "INSERT INTO rooms (id,school_id,school_room_id,building_name,"
                          "room_no,metadata_version) VALUES (:id,'synthetic','r3','test','101',1)",
                          id=UUID(int=111).bytes)
            await execute(conn, "INSERT INTO room_bindings (id,owner_user_id,room_id,status) "
                          "VALUES (:id,:owner,:room,'active')", id=BINDING.bytes,
                          owner=OWNER.bytes, room=UUID(int=111).bytes)
        await accept_history(room, OWNER, BINDING, SimpleNamespace(
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 7),
        ), str(UUID(int=112)), UUID(int=113))
        old = await claim_history(room)
        assert old
        async with school.begin() as conn:
            await execute(conn, "INSERT INTO school_credentials "
                          "(id,owner_user_id,school_id,school_user_id_ciphertext,ciphertext,nonce,"
                          "wrapped_dek,kek_version,algorithm,version,status,verified_at,"
                          "use_allowed) "
                          "VALUES (:id,:owner,'synthetic','synthetic','synthetic',:nonce,"
                          "'synthetic','v1','AES-256-GCM',1,'active',UTC_TIMESTAMP(6),1)",
                          id=CREDENTIAL.bytes, owner=OWNER.bytes, nonce=b"0" * 12)
        ledger, payment = self.payment()
        await ledger.prepare(payment, {})
        assert await ledger.reserve(payment, None)
        await self.effect("school_adapter", "D01")
        async with notification.begin() as conn:
            await execute(conn, "INSERT INTO notification_jobs "
                          "(id,alert_slot_id,owner_user_id,email_ciphertext,generation,email_version,"
                          "template_version,message_id,state,version,attempt_count,next_attempt_at,"
                          "execution_epoch) VALUES (:id,:slot,:owner,'synthetic',1,1,'v1',"
                          "'synthetic-r3-message','pending',1,0,UTC_TIMESTAMP(6),1)",
                          id=JOB.bytes, slot=UUID(int=114).bytes, owner=OWNER.bytes)
        job = await repository.claim(notification, JOB)
        assert await repository.record_permit(notification, job, SendPermit(
            permitted=True, permit_id=UUID(int=115),
            expires_at=datetime.now(UTC) + timedelta(seconds=30), denial_code=None,
        ))
        await repository.mark_body(notification, job)
        await self.effect("notification", "DATA")
        # 保存的只是合成旧执行令牌，不含任何业务Secret或学校载荷。
        return {"epoch": old["execution_epoch"], "lease": old["lease_owner"]}

    async def after(self, saved):
        room, _, notification = (self.engines[name] for name in DOMAINS)
        # 缩短等待：只在已经退出的合成进程租约上推进到期，不是生产恢复命令。
        async with room.begin() as conn:
            await execute(conn, "UPDATE history_sync_windows SET lease_until=UTC_TIMESTAMP(6) "
                          "WHERE state='running'")
        current = await claim_history(room)
        assert current and current["execution_epoch"] > saved["epoch"]
        old = {**current, "execution_epoch": saved["epoch"], "lease_owner": saved["lease"]}
        empty = {"items": [], "request_room_id": "synthetic"}
        assert not await finish_history(room, old, empty, None)
        assert await finish_history(room, current, empty, None)
        ledger, payment = self.payment()
        if await ledger.reserve(payment, None):
            await self.effect("school_adapter", "D01")
        await ledger.settle(payment, error="PROCESS_INTERRUPTED")
        state = await ledger.get(OWNER, ORDER)
        assert state["state"] == "unknown" and state["dispatched_at"]
        async with notification.begin() as conn:
            await execute(conn, "UPDATE notification_jobs SET lease_until=UTC_TIMESTAMP(6) "
                          "WHERE state='sending'")
        assert await recovery.recovery_tick(notification)
        sender = AsyncMock(side_effect=AssertionError("不得重新发送DATA"))
        app = SimpleNamespace(state=SimpleNamespace(database=notification,
                                                    smtp=SimpleNamespace(send=sender)))
        assert not await worker_tick(app, JOB)
        sender.assert_not_awaited()
        assert not await recovery.recovery_tick(notification)
        async with notification.connect() as conn:
            job = await first(conn, "SELECT state,body_started_at FROM notification_jobs "
                              "WHERE id=:id", id=JOB.bytes)
            assert job["state"] == "delivery_unknown" and job["body_started_at"]
        for domain in ("school_adapter", "notification"):
            async with self.engines[domain].connect() as conn:
                assert (await first(conn, "SELECT n FROM r3_effects"))["n"] == 1
        return {"old_epoch_rejected": True, "history_recovered": True,
                "D01_count": 1, "DATA_count": 1, "unknown_preserved": True}

    async def scan(self, *, fail=False):
        async with self.engines["room"].connect() as conn:
            await execute(conn, "SELECT 1")  # 总是成功也不能清掉下面的业务扫描失败。
            await execute(conn, "SELECT id FROM r3_missing_table" if fail else
                          "SELECT id FROM history_sync_windows LIMIT 1")

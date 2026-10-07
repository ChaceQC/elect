"""永久失效会话与暂存敏感载荷的小批边界。"""

import asyncio
import secrets
from datetime import datetime

from login_resource_support import Client, command
from query_resource_support import counts, database, requires_mysql

from services.common.ids import new_id
from services.common.sql import execute, first
from services.identity.application.login import LoginSaga
from services.identity.retention import cleanup
from services.identity.sessions import AppSessions
from services.school_adapter.retention import cleanup as cleanup_staging

pytestmark = requires_mysql


def test_session_seven_day_buffer_detach_terminal_and_never_revive():
    async def case():
        async with database("identity", production_pool=True) as engine:
            sessions = AppSessions(engine, secrets.token_bytes(32))
            client = Client()
            client.release.set()
            saga = LoginSaga(engine, client, sessions)
            token = await saga.login(command(), secrets.token_hex(32), None, new_id())
            assert (await cleanup(engine))["sessions"] == 0
            async with engine.begin() as conn:
                await execute(conn, "UPDATE app_sessions SET expires_at=DATE_SUB(UTC_TIMESTAMP(6),"
                    "INTERVAL 6 DAY),absolute_expires_at=expires_at")
            assert (await cleanup(engine))["sessions"] == 0
            async with engine.begin() as conn:
                await execute(conn, "UPDATE app_sessions SET expires_at=DATE_SUB(UTC_TIMESTAMP(6),"
                    "INTERVAL 8 DAY),absolute_expires_at=expires_at")
            # 仍有未过安全缓冲的登录恢复引用时保留。
            assert (await cleanup(engine))["sessions"] == 0
            async with engine.begin() as conn:
                await execute(conn, "UPDATE login_attempts SET "
                              "expires_at=DATE_SUB(UTC_TIMESTAMP(6),"
                              "INTERVAL 8 DAY)")
            assert (await cleanup(engine, apply=False))["detached"] == 1
            assert await counts(engine, ["app_sessions"]) == [1]
            assert (await cleanup(engine))["sessions"] == 1
            assert await sessions.context(token, required=False) is None
            assert await counts(engine, ["consents", "login_attempts"]) == [1, 1]
            assert (await cleanup(engine))["sessions"] == 0
    asyncio.run(case())


def test_staging_skip_lock_and_preserve_activated_receipt():
    async def case():
        async with database("school_adapter", production_pool=True) as engine:
            ids = [new_id().bytes for _ in range(3)]
            async with engine.begin() as conn:
                for index, key in enumerate(ids):
                    await execute(conn, "INSERT INTO credential_staging (attempt_id,credential_ref,"
                        "encrypted_payload,wrapped_dek,nonce,kek_version,algorithm,candidate_version,"
                        "expires_at,state) VALUES (:id,:id,:value,:value,:nonce,1,'AES-256-GCM',1,"
                        ":expires,:state)", id=key, value=b"synthetic-encrypted", nonce=b"0"*12,
                        expires=datetime(2000 if index < 2 else 2099, 1, 1),
                        state="activated" if index == 0 else "staged")
            assert (await cleanup_staging(engine, apply=False))["staging"] == 2
            async with engine.begin() as reader:
                await execute(reader, "SELECT * FROM credential_staging "
                              "WHERE attempt_id=:id FOR SHARE",
                              id=ids[0])
                assert (await cleanup_staging(engine))["staging"] == 1
            assert (await cleanup_staging(engine))["staging"] == 1
            async with engine.connect() as conn:
                original = await first(conn, "SELECT * FROM credential_staging "
                                       "WHERE attempt_id=:id",
                                       id=ids[0])
                assert original["state"] == "activated" and original["encrypted_payload"] == b""
            assert (await cleanup_staging(engine))["staging"] == 0
    asyncio.run(case())

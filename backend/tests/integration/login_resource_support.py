"""R1隔离登录夹具：只模拟领域调用，登录事务/会话/命名锁均走生产实现。"""

import asyncio
import secrets
from datetime import UTC, datetime, timedelta

from services.common.ids import new_id
from services.identity.agreement import agreement
from services.identity.dto import LoginRequest


def command():
    return LoginRequest(student_id="synthetic", password="synthetic",
                        challenge_id=secrets.token_urlsafe(32), captcha_answer="1234",
                        agreement_version=agreement().version, agreement_accepted=True,
                        credential_use_allowed=True)


class Client:
    def __init__(self):
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.refs = {}
        self.authentications = 0

    async def call(self, service, path, scope, request_id, payload, **kwargs):
        if path in {"/login-attempts/authenticate", "/login-attempts/status"}:
            self.authentications += path.endswith("authenticate")
            self.entered.set()
            await self.release.wait()
            return {"attempt_id": payload["attempt_id"],
                    "credential_ref": self.refs.setdefault(payload["attempt_id"], new_id()),
                    "credential_version": 1, "lookup_aliases": {},
                    "expires_at": datetime.now(UTC) + timedelta(minutes=10)}
        assert path in {"/credentials/prepare-update", "/credentials/activate",
                        "/credentials/commit-update"}
        return {}


async def child_lock(url, identifier):
    from uuid import UUID

    from services.common.database import create_database
    from services.common.http import ApiError
    from services.identity.application.login import LoginSaga

    engine = create_database(url)
    try:
        async with LoginSaga(engine, None, None).locked(UUID(identifier)):
            print("acquired", flush=True)
    except ApiError as error:
        assert error.status == 429
        print("busy", flush=True)
    finally:
        await engine.dispose()

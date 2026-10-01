import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.school_adapter.application.sessions import SchoolSessions
from services.school_adapter.infrastructure.crypto import KeyRing


class Repository:
    def __init__(self, allowed=True):
        self.row = {"id": new_id().bytes, "version": 1, "status": "active", "use_allowed": allowed}

    async def current(self, owner):
        return self.row.copy()

    def payload(self, row):
        return {
            "student_id": "synthetic",
            "password": "synthetic-password",
            "school_user_id": "0001",
        }

    async def require_reauth(self, row, request_id):
        self.row["status"] = "requires_reauth"


class Store:
    def __init__(self, token="old"):
        self.token = token

    async def get_secret(self, key):
        return {"token": self.token} if self.token else None

    async def put_secret(self, key, value):
        self.token = value["token"]

    async def call(self, method, key):
        assert method == "delete"
        self.token = None

    async def rate(self, *args, **kwargs):
        pass

    @asynccontextmanager
    async def account_lock(self, *args, **kwargs):
        yield


class Protocol:
    def __init__(self, failures):
        self.failures, self.reads, self.auths = failures, 0, 0

    async def read(self, *args, **kwargs):
        self.reads += 1
        if self.failures:
            code = self.failures.pop(0)
            raise ApiError(
                409 if code == ErrorCode.SCHOOL_REAUTH_REQUIRED else 503, code, "synthetic"
            )
        return {"data": []}

    async def challenge(self, **kwargs):
        return SimpleNamespace(image="synthetic", uid="synthetic", cookies=[])

    async def authenticate(self, *args, **kwargs):
        self.auths += 1
        return "new", "0001"


def sessions(repo, store, protocol):
    return SchoolSessions(
        repo, store, protocol, KeyRing("v1", {"v1": b"x" * 32}), solver=lambda x: "3"
    )


def test_transient_get_retries_once_in_shared_budget():
    async def run():
        repo, store, protocol = Repository(), Store(), Protocol([ErrorCode.SCHOOL_UNAVAILABLE])
        assert await sessions(repo, store, protocol).read(new_id(), new_id(), "/rooms", {}) == {
            "data": []
        }
        assert protocol.reads == 2 and protocol.auths == 0

    asyncio.run(run())


def test_second_auth_failure_stops_retry_and_marks_requires_reauth():
    async def run():
        repo, store = Repository(), Store()
        protocol = Protocol([ErrorCode.SCHOOL_REAUTH_REQUIRED] * 2)
        with pytest.raises(ApiError):
            await sessions(repo, store, protocol).read(new_id(), new_id(), "/rooms", {})
        assert protocol.reads == 2 and protocol.auths == 1
        assert repo.row["status"] == "requires_reauth" and store.token is None

    asyncio.run(run())


def test_denied_background_authorization_never_submits_password():
    async def run():
        repo, store, protocol = Repository(allowed=False), Store(token=None), Protocol([])
        with pytest.raises(ApiError):
            await sessions(repo, store, protocol).read(new_id(), new_id(), "/rooms", {})
        assert protocol.reads == 0 and protocol.auths == 0
        assert repo.row["status"] == "requires_reauth"

    asyncio.run(run())

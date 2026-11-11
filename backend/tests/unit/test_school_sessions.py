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
        self.engine = None

    async def current(self, owner):
        return self.row.copy()

    def payload(self, row):
        return {
            "student_id": "synthetic",
            "password": "synthetic-password",
            "school_user_id": "0001",
        }

    async def require_reauth(self, row, request_id):
        if (self.row["id"], self.row["version"], self.row["status"]) == (
            row["id"], row["version"], "active"
        ):
            self.row["status"] = "requires_reauth"


class Store:
    def __init__(self, token="old"):
        self.token = token
        self.condition = asyncio.Condition()
        self.readers = self.balance_readers = self.waiting_writers = 0
        self.writer = False

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
        async with self.condition:
            self.waiting_writers += 1
            try:
                await self.condition.wait_for(lambda: not self.writer and not self.readers)
                self.writer = True
            finally:
                self.waiting_writers -= 1
        try:
            yield
        finally:
            async with self.condition:
                self.writer = False
                self.condition.notify_all()

    @asynccontextmanager
    async def account_read(self, alias, *, deadline, balance=False):
        async with self.condition:
            await self.condition.wait_for(
                lambda: not self.writer and not self.waiting_writers and self.readers < 2
                and (not balance or not self.balance_readers)
            )
            self.readers += 1
            self.balance_readers += balance
        try:
            yield
        finally:
            async with self.condition:
                self.readers -= 1
                self.balance_readers -= balance
                self.condition.notify_all()


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


def test_revocation_during_cache_write_discards_late_token():
    async def run():
        repo, store, protocol = Repository(), Store(token=None), Protocol([])
        original = store.put_secret

        async def revoke_before_write(key, value):
            repo.row["status"] = "revoked"
            await original(key, value)

        store.put_secret = revoke_before_write
        with pytest.raises(ApiError) as result:
            await sessions(repo, store, protocol).read(new_id(), new_id(), "/rooms", {})
        assert result.value.code == ErrorCode.SCHOOL_REAUTH_REQUIRED
        assert store.token is None and protocol.reads == 0

    asyncio.run(run())


def test_two_reads_overlap_for_one_account():
    async def run():
        repo, store = Repository(), Store()
        entered, release = asyncio.Event(), asyncio.Event()

        class ConcurrentProtocol(Protocol):
            async def read(self, *args, **kwargs):
                self.reads += 1
                if self.reads == 2:
                    entered.set()
                await release.wait()
                return {"data": []}

        protocol = ConcurrentProtocol([])
        adapter, owner = sessions(repo, store, protocol), new_id()
        first = asyncio.create_task(adapter.read(owner, new_id(), "/history", {}))
        second = asyncio.create_task(adapter.read(owner, new_id(), "/payments", {}))
        await asyncio.wait_for(entered.wait(), 2)
        assert store.readers == 2
        release.set()
        assert await asyncio.wait_for(asyncio.gather(first, second), 2) == [
            {"data": []}, {"data": []}
        ]

    asyncio.run(run())


def test_concurrent_expired_tokens_refresh_once_without_lock_upgrade():
    async def run():
        repo, store = Repository(), Store()
        both_expired = asyncio.Event()

        class ExpiredProtocol(Protocol):
            def __init__(self):
                super().__init__([])
                self.expired = 0

            async def read(self, path, token, query, **kwargs):
                self.reads += 1
                if token == "old":
                    self.expired += 1
                    if self.expired == 2:
                        both_expired.set()
                    await both_expired.wait()
                    raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "synthetic")
                return {"data": []}

            async def authenticate(self, *args, **kwargs):
                assert store.writer and store.readers == 0
                return await super().authenticate(*args, **kwargs)

        protocol = ExpiredProtocol()
        adapter, owner = sessions(repo, store, protocol), new_id()
        values = await asyncio.wait_for(asyncio.gather(
            adapter.read(owner, new_id(), "/history", {}),
            adapter.read(owner, new_id(), "/payments", {}),
        ), 2)
        assert values == [{"data": []}, {"data": []}]
        assert protocol.reads == 4 and protocol.auths == 1
        assert repo.row["status"] == "active" and store.token == "new"

    asyncio.run(run())


@pytest.mark.parametrize("changed_version", [False, True])
def test_late_second_auth_failure_preserves_new_cache_and_credential(changed_version):
    async def run():
        repo, store = Repository(), Store()
        protocol = Protocol([ErrorCode.SCHOOL_REAUTH_REQUIRED] * 2)
        adapter, owner = sessions(repo, store, protocol), new_id()
        observed, refreshed = asyncio.Event(), asyncio.Event()
        original_lock = store.account_lock
        late_task = None

        @asynccontextmanager
        async def delayed_lock(*args, **kwargs):
            if asyncio.current_task() is late_task and protocol.reads == 2:
                await refreshed.wait()
            async with original_lock(*args, **kwargs):
                yield

        async def observer(value, error, observed_at):
            assert store.balance_readers == 1
            assert error == ErrorCode.SCHOOL_REAUTH_REQUIRED
            observed.set()
            return "observed"

        async def refresh():
            await observed.wait()
            async with original_lock("synthetic"):
                if changed_version:
                    repo.row["version"] += 1
                store.token = "newer"
            refreshed.set()

        store.account_lock = delayed_lock
        late_task = asyncio.create_task(
            adapter.read(owner, new_id(), "/rooms", {}, observer=observer, balance=True)
        )
        result, _ = await asyncio.wait_for(asyncio.gather(late_task, refresh()), 2)
        assert result == "observed"
        assert protocol.reads == 2 and protocol.auths == 1
        assert repo.row["status"] == "active" and store.token == "newer"

    asyncio.run(run())


@pytest.mark.parametrize("fail_first", [False, True])
def test_bound_observer_holds_balance_permit_until_success_or_failure(monkeypatch, fail_first):
    async def run():
        repo, store = Repository(), Store()
        failures = [ErrorCode.SCHOOL_UNAVAILABLE] * 2 if fail_first else []
        protocol = Protocol(failures)
        adapter, owner, request_id = sessions(repo, store, protocol), new_id(), new_id()
        entered, release = asyncio.Event(), asyncio.Event()
        errors = []

        async def observe(engine, observed_owner, observed_request, value, error, observed_at):
            assert store.balance_readers == 1
            errors.append(error)
            if observed_request == request_id:
                entered.set()
                await release.wait()
            return error

        monkeypatch.setattr(
            "services.school_adapter.infrastructure.balance_observations.observe", observe
        )
        monkeypatch.setattr(
            "services.school_adapter.application.sessions.random.uniform", lambda *_: 0
        )
        first = asyncio.create_task(adapter.read_bound(owner, request_id))
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(adapter.read_bound(owner, new_id()))
        await asyncio.sleep(0)
        assert store.balance_readers == 1 and not second.done()
        assert protocol.reads == (2 if fail_first else 1)
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 2)
        assert errors == [ErrorCode.SCHOOL_UNAVAILABLE if fail_first else None, None]
        assert protocol.reads == (3 if fail_first else 2)

    asyncio.run(run())


def test_recovery_failure_after_read_observes_inside_balance_permit():
    async def run():
        repo, store = Repository(allowed=False), Store()
        protocol = Protocol([ErrorCode.SCHOOL_REAUTH_REQUIRED])

        async def observer(value, error, observed_at):
            assert store.balance_readers == 1
            assert error == ErrorCode.SCHOOL_REAUTH_REQUIRED
            return "observed"

        result = await sessions(repo, store, protocol).read(
            new_id(), new_id(), "/rooms", {}, observer=observer, balance=True
        )
        assert result == "observed" and protocol.reads == 1 and protocol.auths == 0
        assert repo.row["status"] == "requires_reauth"

    asyncio.run(run())


def test_revocation_after_refresh_observes_failure_before_another_send():
    async def run():
        repo, store = Repository(), Store()
        protocol = Protocol([ErrorCode.SCHOOL_REAUTH_REQUIRED])
        original_read = store.account_read

        @asynccontextmanager
        async def revoke_on_resume(*args, **kwargs):
            async with original_read(*args, **kwargs):
                if protocol.auths:
                    repo.row["status"] = "revoked"
                yield

        async def observer(value, error, observed_at):
            assert store.balance_readers == 1
            assert error == ErrorCode.SCHOOL_REAUTH_REQUIRED
            return "observed"

        store.account_read = revoke_on_resume
        result = await sessions(repo, store, protocol).read(
            new_id(), new_id(), "/rooms", {}, observer=observer, balance=True
        )
        assert result == "observed" and protocol.reads == 1 and protocol.auths == 1

    asyncio.run(run())

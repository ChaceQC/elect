import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import ActivateCredential
from services.school_adapter.application.authentication import Authentication
from services.school_adapter.infrastructure.credentials import CredentialRepository
from services.school_adapter.infrastructure.crypto import (
    EnvelopeCrypto,
    KeyRing,
    credential_aad,
    lookup_aliases,
)


class Store:
    def __init__(self, alias):
        self.alias = alias
        self.guard = asyncio.Lock()
        self.waiting = asyncio.Event()
        self.holding = False
        self.values = {}
        self.writes = []
        self.on_write = None
        self.on_acquire = None

    @asynccontextmanager
    async def account_lock(self, alias, *, deadline):
        assert alias == self.alias
        assert 0 < deadline.remaining() <= 5
        self.waiting.set()
        async with self.guard:
            self.holding = True
            try:
                if self.on_acquire:
                    self.on_acquire()
                yield
            finally:
                self.holding = False

    async def get_secret(self, key):
        assert self.holding
        return self.values.get(key)

    async def put_secret(self, key, value):
        assert self.holding
        self.values[key] = value
        self.writes.append(key)
        if self.on_write:
            self.on_write()

    async def call(self, method, key):
        assert self.holding and method == "delete"
        self.values.pop(key, None)


class Repository(CredentialRepository):
    def __init__(self, command, store, lookup, *, activated=False, erased=False):
        super().__init__(None, EnvelopeCrypto(KeyRing("v1", {"v1": b"e" * 32})))
        self.command, self.store = command, store
        self.value = {
            "student_id": "synthetic",
            "school_user_id": "synthetic-user",
            "aliases": lookup_aliases(lookup, "hbue", "synthetic"),
        }
        encrypted = self.crypto.encrypt(
            self.value, credential_aad(command.credential_ref, command.attempt_id, 1)
        )
        self.stage_row = {
            **encrypted,
            "attempt_id": command.attempt_id.bytes,
            "credential_ref": command.credential_ref.bytes,
            "candidate_version": 1,
            "expires_at": datetime.now(UTC) + timedelta(minutes=10),
            "state": "activated" if activated else "staged",
            "owner_user_id": command.owner_user_id.bytes if activated else None,
            "encrypted_payload": b"" if erased else encrypted["ciphertext"],
        }
        self.row = None
        self.activation_locks = []
        if activated:
            self.make_active()

    def make_active(self):
        command = self.command
        encrypted = self.crypto.encrypt(
            self.value, credential_aad(command.credential_ref, command.owner_user_id, 1)
        )
        self.row = {
            **encrypted,
            "id": command.credential_ref.bytes,
            "owner_user_id": command.owner_user_id.bytes,
            "version": 1,
            "status": "active",
        }

    async def staged(self, attempt_id):
        assert attempt_id == self.command.attempt_id
        return self.stage_row.copy() if self.stage_row else None

    async def activate(self, command):
        self.activation_locks.append(self.store.holding)
        if self.stage_row["state"] not in {"staged", "activated"}:
            raise ApiError(400, ErrorCode.CAPTCHA_EXPIRED, "登录暂存已过期，请重新认证")
        if self.stage_row["state"] == "activated":
            return self.stage_row["candidate_version"]
        assert self.store.holding
        self.make_active()
        self.stage_row.update(state="activated", owner_user_id=command.owner_user_id.bytes)
        return 1

    async def current(self, owner):
        assert owner == self.command.owner_user_id
        return self.row.copy()


def setup(*, activated=False, erased=False):
    command = ActivateCredential(
        attempt_id=new_id(),
        owner_user_id=new_id(),
        request_id=new_id(),
        credential_ref=new_id(),
        expected_credential_version=None,
        credential_use_allowed=True,
    )
    lookup = KeyRing("v1", {"v1": b"l" * 32})
    alias = lookup_aliases(lookup, "hbue", "synthetic")["v1"]
    store = Store(alias)
    repository = Repository(command, store, lookup, activated=activated, erased=erased)
    staged_key = f"school_adapter:staged_token:{command.attempt_id}"
    token_key = f"school_adapter:token:{command.credential_ref}:1"
    store.values[staged_key] = {"token": "staged-token"}
    auth = Authentication(repository, store, None, lookup)
    return command, auth, repository, store, token_key


@pytest.mark.parametrize("activated,erased", [(False, False), (True, False), (True, True)])
def test_activation_publishes_when_cache_missing(activated, erased):
    async def run():
        command, auth, repository, store, token_key = setup(activated=activated, erased=erased)
        result = await auth.activate(command)
        assert result == {
            "credential_ref": str(command.credential_ref),
            "credential_version": 1,
            "state": "active",
        }
        assert repository.activation_locks == ([False, True] if erased else [True])
        assert store.values[token_key] == {"token": "staged-token"}
        assert store.writes == [token_key]

    asyncio.run(run())


@pytest.mark.parametrize("erased", [False, True])
def test_activation_replay_waits_and_preserves_refreshed_token(erased):
    async def run():
        command, auth, repository, store, token_key = setup(activated=True, erased=erased)
        async with store.guard:
            task = asyncio.create_task(auth.activate(command))
            await asyncio.wait_for(store.waiting.wait(), timeout=1)
            assert not task.done()
            assert repository.activation_locks == ([False] if erased else [])
            store.values[token_key] = {"token": "refreshed-token"}
        await task
        assert repository.activation_locks == ([False, True] if erased else [True])
        assert store.values[token_key] == {"token": "refreshed-token"}
        assert store.writes == []

    asyncio.run(run())


@pytest.mark.parametrize("erased", [False, True])
@pytest.mark.parametrize("status,version", [("active", 2), ("revoked", 1)])
def test_activation_rejects_changed_or_revoked_credential(status, version, erased):
    async def run():
        command, auth, repository, store, token_key = setup(activated=True, erased=erased)
        repository.row.update(status=status, version=version)
        with pytest.raises(ApiError) as result:
            await auth.activate(command)
        assert result.value.code == ErrorCode.VERSION_CONFLICT
        assert token_key not in store.values and not store.writes

    asyncio.run(run())


def test_revocation_during_publication_removes_late_token():
    async def run():
        command, auth, repository, store, token_key = setup(activated=True)
        store.on_write = lambda: repository.row.update(status="revoked")
        with pytest.raises(ApiError) as result:
            await auth.activate(command)
        assert result.value.code == ErrorCode.SCHOOL_REAUTH_REQUIRED
        assert token_key not in store.values

    asyncio.run(run())


@pytest.mark.parametrize("erased", [False, True])
def test_revocation_while_waiting_keeps_repository_rejection(erased):
    async def run():
        command, auth, repository, store, token_key = setup(activated=True, erased=erased)
        store.on_acquire = lambda: repository.stage_row.update(
            state="expired", encrypted_payload=b""
        )
        with pytest.raises(ApiError) as result:
            await auth.activate(command)
        assert result.value.code == ErrorCode.CAPTCHA_EXPIRED
        assert token_key not in store.values and not store.writes

    asyncio.run(run())


@pytest.mark.parametrize("case", ["missing", "wrong_ref", "wrong_owner", "revoked"])
def test_activation_preserves_staging_rejections(case):
    async def run():
        command, auth, repository, store, _ = setup(activated=True)
        if case == "missing":
            repository.stage_row = None
        elif case == "wrong_ref":
            repository.stage_row["credential_ref"] = new_id().bytes
        elif case == "wrong_owner":
            repository.stage_row["owner_user_id"] = new_id().bytes
        else:
            repository.stage_row.update(state="expired", encrypted_payload=b"")
        with pytest.raises(ApiError) as result:
            await auth.activate(command)
        assert result.value.code == (
            ErrorCode.CAPTCHA_EXPIRED if case == "revoked" else ErrorCode.NOT_FOUND
        )
        assert repository.activation_locks == [] and not store.writes

    asyncio.run(run())

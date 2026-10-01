from contextlib import AsyncExitStack

from redis.exceptions import ConnectionError

from services.common.http import ApiError
from services.school_adapter.infrastructure.redis_store import SharedStore
from services.school_adapter.infrastructure.transport import Deadline


async def verify_shared_limits(store):
    async with AsyncExitStack() as held:
        for _ in range(4):
            await held.enter_async_context(store.global_slot(Deadline(2), pool="background"))
        try:
            async with store.global_slot(Deadline(0.1), pool="background"):
                raise AssertionError("后台占用了人工认证保留资源")
        except ApiError as error:
            assert error.code == "SCHOOL_TIMEOUT"
        await held.enter_async_context(store.global_slot(Deadline(2)))
        assert await store.call("zcard", "school_adapter:global_slots") == 5
    assert await store.call("zcard", "school_adapter:global_slots") == 0

    class Disconnected:
        async def eval(self, *args):
            raise ConnectionError("synthetic redis fault")

    unavailable = SharedStore(Disconnected(), store.crypto)
    try:
        await unavailable.create_challenge("0" * 64, None)
    except ApiError as error:
        assert error.code == "DEPENDENCY_UNAVAILABLE" and error.status == 503
    else:
        raise AssertionError("Redis 失效时未阻断学校认证")
    print("共享五并发/四后台/人工保留资源、Redis 故障 fail-closed：通过")

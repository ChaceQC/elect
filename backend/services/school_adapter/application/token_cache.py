"""缓存写入前后复核持久授权，撤回与重认证期间的迟到 token 不可继续使用。"""

from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError


async def cache_token(repository, store, owner, credential, version, value):
    key = f"school_adapter:token:{credential}:{version}"
    row = await repository.current(owner)
    if row["id"] != credential.bytes or row["version"] != version or row["status"] != "active":
        raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化，请重新认证")
    await store.put_secret(key, value)
    latest = await repository.current(owner)
    if (
        latest["id"] != credential.bytes
        or latest["version"] != version
        or latest["status"] != "active"
    ):
        await store.call("delete", key)
        raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化，请重新认证")
    return latest


async def clear_revoked_tokens(repository, store, credential, version):
    from services.common.sql import execute

    async with repository.engine.connect() as conn:
        rows = (
            (
                await execute(
                    conn,
                    "SELECT attempt_id,candidate_version FROM credential_staging "
                    "WHERE credential_ref=:id AND state='expired'",
                    id=credential.bytes,
                )
            )
            .mappings()
            .all()
        )
    # 重放旧撤回只清理已失效暂存与旧版本缓存，不触及随后重新授权的新版本。
    versions = {version} | {
        row["candidate_version"] for row in rows if row["candidate_version"] <= version
    }
    keys = [f"school_adapter:token:{credential}:{item}" for item in versions]
    keys += [f"school_adapter:staged_token:{UUID(bytes=row['attempt_id'])}" for row in rows]
    await store.call("delete", *keys)

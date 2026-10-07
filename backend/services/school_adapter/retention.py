"""已过期暂存只擦除敏感载荷；保留激活回执、当前凭据和未知学校写。"""

from datetime import datetime

from services.common.sql import execute


async def cleanup(engine, *, apply=True, limit=200, cutoff=None):
    async with engine.begin() as conn:
        rows = (await execute(conn, "SELECT attempt_id FROM credential_staging WHERE "
            "expires_at<=UTC_TIMESTAMP(6) AND state IN ('staged','expired','activated') "
            "AND LENGTH(encrypted_payload)>0 AND expires_at<=:cutoff "
            "ORDER BY state,expires_at,attempt_id LIMIT :limit FOR UPDATE SKIP LOCKED",
            limit=max(1, min(limit, 200)), cutoff=cutoff or datetime.max)).mappings().all()
        if apply:
            for row in rows:
                await execute(conn, "UPDATE credential_staging SET "
                    "state=IF(state='activated','activated','expired'),encrypted_payload='',"
                    "wrapped_dek='',updated_at=UTC_TIMESTAMP(6) WHERE attempt_id=:id",
                    id=row["attempt_id"])
    return {"candidates": len(rows), "staging": len(rows), "applied": apply}

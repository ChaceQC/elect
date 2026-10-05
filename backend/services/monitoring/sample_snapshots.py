"""固定成员快照的复用与受理；库内仅保存 token hash。"""

import base64
import hashlib
import hmac

from sqlalchemy import text

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .repository import lock_monitor

MAX_SAMPLES = 20_000
MAX_SNAPSHOTS = 12
MAX_MEMBERS = 60_000
CREATIONS_PER_MINUTE = 6


def token_for(key, owner, snapshot_id):
    payload = b"elect:sample-snapshot:v1\0" + owner.bytes + snapshot_id
    return base64.urlsafe_b64encode(hmac.digest(key, payload, "sha256")).decode().rstrip("=")


def limited(message, retry=60):
    return ApiError(429, ErrorCode.RATE_LIMITED, message, True, retry_after_seconds=retry)


async def create_or_reuse(conn, owner, command, start, end, token_key):
    # 第一次一致性读必须在用户锁之后，避免并发请求读到旧的配额快照。
    await lock_monitor(conn, owner)
    members = (await execute(
        conn, "SELECT id FROM monitor_samples WHERE owner_user_id=:owner "
        "AND binding_id=:binding AND captured_at>=:start AND captured_at<:end "
        "ORDER BY captured_at DESC,id DESC LIMIT :limit",
        owner=owner.bytes, binding=command.binding_id.bytes, start=start, end=end,
        limit=MAX_SAMPLES + 1,
    )).scalars().all()
    if len(members) > MAX_SAMPLES:
        raise limited("采集记录过多，请缩小日期范围")
    digest = hashlib.sha256(b"".join(members)).digest()
    candidates = (await execute(
        conn, "SELECT * FROM sample_snapshots WHERE owner_user_id=:owner "
        "AND binding_id=:binding AND start_date=:start AND end_date=:end "
        "AND membership_hash=:digest AND expires_at>UTC_TIMESTAMP(6) "
        "ORDER BY created_at DESC LIMIT :limit FOR SHARE",
        owner=owner.bytes, binding=command.binding_id.bytes, start=command.start_date,
        end=command.end_date, digest=digest, limit=MAX_SNAPSHOTS,
    )).mappings().all()
    for row in candidates:
        token = token_for(token_key, owner, row["id"])
        if hmac.compare_digest(hashlib.sha256(token.encode()).digest(), row["token_hash"]):
            return token, row
    await check_budget(conn, owner, len(members))
    return await create_snapshot(conn, owner, command, members, digest, token_key)


async def check_budget(conn, owner, size):
    budget = await first(
        conn, "SELECT COUNT(*) AS snapshots,COALESCE(SUM(total),0) AS members,"
        "COALESCE(SUM(created_at>DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 MINUTE)),0) "
        "AS recent FROM sample_snapshots WHERE owner_user_id=:owner",
        owner=owner.bytes,
    )
    if (budget["snapshots"] >= MAX_SNAPSHOTS or budget["members"] + size > MAX_MEMBERS
            or budget["recent"] >= CREATIONS_PER_MINUTE):
        raise limited("采集查询过于频繁，请稍后重试")


async def create_snapshot(conn, owner, command, members, digest, token_key):
    snapshot_id = new_id().bytes
    token = token_for(token_key, owner, snapshot_id)
    await execute(
        conn, "INSERT INTO sample_snapshots (id,owner_user_id,binding_id,start_date,"
        "end_date,token_hash,membership_hash,total,expires_at) VALUES "
        "(:id,:owner,:binding,:start,:end,:hash,:digest,:total,"
        "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 MINUTE))",
        id=snapshot_id, owner=owner.bytes, binding=command.binding_id.bytes,
        start=command.start_date, end=command.end_date,
        hash=hashlib.sha256(token.encode()).digest(), digest=digest, total=len(members),
    )
    # 固定刚才读到的实际集合；不用再次 INSERT SELECT 纳入迟到提交。
    for offset in range(0, len(members), 500):
        await conn.execute(
            text("INSERT INTO sample_snapshot_items (snapshot_id,position,sample_id) "
                 "VALUES (:snapshot,:position,:sample)"),
            [{"snapshot": snapshot_id, "position": index + 1, "sample": member}
             for index, member in enumerate(members[offset:offset + 500], offset)],
        )
    return token, await first(conn, "SELECT * FROM sample_snapshots WHERE id=:id", id=snapshot_id)

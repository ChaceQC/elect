"""同库压缩冷归档；校验格式、数量、摘要及读回，不缓存去重缺失。"""

import hashlib
import json
import zlib
from datetime import date, datetime
from decimal import Decimal

from .errors import ErrorCode
from .http import ApiError
from .ids import new_id
from .sql import execute, first

MAX_BYTES = 2 * 1024 * 1024


def encode_value(value):
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    raise TypeError("不支持的归档类型")


def decode_value(value):
    if len(value) == 1:
        for key, convert in (("$bytes", bytes.fromhex), ("$datetime", datetime.fromisoformat),
                             ("$date", date.fromisoformat), ("$decimal", Decimal)):
            if key in value:
                return convert(value[key])
    return value


def unavailable():
    return ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "原请求归档暂不可读取，请保留原请求", True)


def unpack(record):
    try:
        if record["format_version"] != 1 or record["row_count"] != 1:
            raise ValueError("归档版本或数量错误")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(record["payload"], MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or not decoder.eof or decoder.unused_data:
            raise ValueError("归档大小或格式错误")
        if hashlib.sha256(raw).digest() != record["content_hash"]:
            raise ValueError("归档摘要不匹配")
        value = json.loads(raw, object_hook=decode_value)
        if not isinstance(value, dict):
            raise ValueError("归档对象错误")
        return value
    except Exception:
        raise unavailable() from None


async def save(conn, kind, object_key, row):
    raw = json.dumps(dict(row), default=encode_value, sort_keys=True,
                     ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise unavailable()
    digest = hashlib.sha256(raw).digest()
    await execute(
        conn, "INSERT IGNORE INTO archive_records "
        "(id,kind,object_key,format_version,row_count,content_hash,payload) "
        "VALUES (:id,:kind,:key,1,1,:hash,:payload)", id=new_id().bytes,
        kind=kind, key=object_key, hash=digest, payload=zlib.compress(raw),
    )
    stored = await first(conn, "SELECT * FROM archive_records WHERE kind=:kind AND object_key=:key",
                         kind=kind, key=object_key)
    if stored["content_hash"] != digest or unpack(stored) != dict(row):
        raise unavailable()
    return stored["id"]


async def read(conn, archive_id):
    row = await first(conn, "SELECT * FROM archive_records WHERE id=:id", id=archive_id)
    if not row:
        raise unavailable()
    return unpack(row)


async def read_object(conn, kind, object_key):
    row = await first(conn, "SELECT * FROM archive_records WHERE kind=:kind AND object_key=:key",
                      kind=kind, key=object_key)
    return unpack(row) if row else None


async def request_key(conn, owner, kind, key_hash, digest):
    row = await first(conn, "SELECT * FROM cold_request_keys WHERE owner_user_id=:owner "
                      "AND kind=:kind AND key_hash=:key", owner=owner.bytes,
                      kind=kind, key=key_hash)
    if not row:
        return None
    if row["request_digest"] != digest:
        raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "该键已用于不同请求")
    archived = await read(conn, row["archive_id"])
    result = archived.get("run_id", archived.get("operation_id", archived.get("id")))
    key = archived.get("key_hash", archived.get("idempotency_key_hash"))
    if (archived.get("owner_user_id") != owner.bytes or key != key_hash
            or archived.get("request_digest") != digest or result != row["result_id"]):
        raise unavailable()
    return row["result_id"]


async def retain_key(conn, owner, kind, key_hash, digest, result, archive):
    await execute(conn, "INSERT INTO cold_request_keys "
                  "(owner_user_id,kind,key_hash,request_digest,result_id,archive_id) "
                  "VALUES (:owner,:kind,:key,:digest,:result,:archive)", owner=owner,
                  kind=kind, key=key_hash, digest=digest, result=result, archive=archive)

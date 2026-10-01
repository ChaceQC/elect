"""使用本人已激活凭据验证真实后台恢复；不复制或打印认证材料。"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from scripts.auth_file import read_auth
from services.common.database import create_database
from services.common.ids import new_id
from services.common.runtime import Runtime, read_secret
from services.common.security import Principal
from services.common.service_client import ServiceClient
from services.common.sql import first
from services.school_adapter.infrastructure.crypto import KeyRing, lookup_aliases


async def verify(path, record):
    record["stage"] = "load_credentials"
    student, password = read_auth(path)
    del password
    aliases = lookup_aliases(
        KeyRing.load("/run/secrets/school_lookup_hmac_bundle"), "hbue", student
    )
    del student
    adapter = Runtime.model_validate_json(read_secret("/run/secrets/school_adapter_runtime.json"))
    runtime = Runtime.model_validate_json(read_secret("/run/secrets/room_runtime.json"))
    engine = create_database(adapter.db_url.get_secret_value())
    cache = Redis.from_url(adapter.redis_url.get_secret_value())
    client = ServiceClient(runtime)
    try:
        record["stage"] = "lookup_active_credential"
        async with engine.connect() as conn:
            version, digest = next(iter(aliases.items()))
            row = await first(
                conn,
                "SELECT c.id,c.owner_user_id,c.version,c.status,c.use_allowed FROM "
                "account_lookup a JOIN school_credentials c ON c.id=a.credential_id "
                "WHERE a.school_id='hbue' AND a.key_version=:version AND a.lookup_hash=:hash",
                version=version,
                hash=bytes.fromhex(digest),
            )
        if not row or row["status"] != "active" or not row["use_allowed"]:
            record["credential_found"] = bool(row)
            record["credential_state"] = row["status"] if row else None
            record["background_allowed"] = bool(row["use_allowed"]) if row else None
            raise RuntimeError("没有本人已授权的激活凭据")
        credential, owner = UUID(bytes=row["id"]), UUID(bytes=row["owner_user_id"])
        await cache.delete(f"school_adapter:token:{credential}:{row['version']}")
        record["stage"] = "background_read"
        request_id = new_id()
        response = await client.call(
            "school_adapter",
            "/rooms/bound",
            "school:rooms",
            request_id,
            principal=Principal("room", owner, 1, request_id),
        )
        async with engine.connect() as conn:
            latest = await first(
                conn,
                "SELECT status,version FROM school_credentials WHERE id=:id",
                id=credential.bytes,
            )
        assert latest["status"] == "active" and latest["version"] == row["version"]
        record.update(
            background_reauthentication="passed",
            bound_room_count=len(response["items"]),
            credential_version_unchanged=True,
            application_session_required=False,
        )
    finally:
        await client.close()
        await cache.aclose()
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-file", type=Path, required=True)
    args = parser.parse_args()
    record = {
        "date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "source": "正式 School Adapter + 真实学校 + 本人已授权密文",
        "scope": ["A01", "A02", "A03", "A04", "B01", "B02"],
        "external_business_writes": False,
    }
    try:
        asyncio.run(verify(args.auth_file, record))
        record["result"] = "passed"
    except Exception as error:
        record.update(
            result="failed",
            failure_class=type(error).__name__,
            failure_code=getattr(error, "code", None),
        )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    if record["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

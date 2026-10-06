from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute


async def recover_tick(app, *, stop=None):
    from .revocation import recover_revocation

    try:
        if await recover_revocation(app):
            return True
    except ApiError as error:
        if error.code != ErrorCode.RATE_LIMITED:
            raise
        return False
    if stop and stop.is_set():
        return False
    async with app.state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE login_attempts SET state='expired',updated_at=UTC_TIMESTAMP(6) "
            "WHERE expires_at <= UTC_TIMESTAMP(6) AND state IN "
            "('created','authenticating','staged')",
        )
        rows = (
            (
                await execute(
                    conn,
                    "SELECT id FROM login_attempts WHERE state IN "
                    "('authenticating','staged','identity_committed','activating') "
                    "AND next_reconcile_at<=UTC_TIMESTAMP(6) "
                    "AND updated_at<DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 5 SECOND) "
                    "ORDER BY next_reconcile_at LIMIT 5",
                )
            )
            .mappings()
            .all()
        )
    saga = app.state.login_saga
    for item in rows:
        if stop and stop.is_set():
            break
        attempt_id = UUID(bytes=item["id"])
        try:
            async with saga.locked(attempt_id, background=True):
                row = await saga.read(attempt_id)
                if row["state"] not in {
                    "authenticating",
                    "staged",
                    "identity_committed",
                    "activating",
                }:
                    continue
                await saga.advance(row, new_id())
        except ApiError as error:
            if (
                error.code not in {ErrorCode.NOT_FOUND, ErrorCode.RATE_LIMITED}
                and error.status < 500
            ):
                current = await saga.read(attempt_id)
                if current["state"] not in {"identity_committed", "activating"}:
                    await saga.state(attempt_id, "failed", error=error.code)
    return bool(rows)
